/**
 * app.js — ShowingDay Agent UI
 * Full frontend for the showing day planning tool.
 * Manages all screens, API calls, route display, and session state.
 */

'use strict';

// ── App State ──────────────────────────────────────────────────────────────────
const AppState = {
  currentScreen: 'start',
  session: null,
  config: {},
  client: null,
  addresses: [],
  route: null,
  map: null,
  mapMarkers: [],
  mapPolyline: null,
  lastPollHash: '',
  pollInterval: null,
  pendingAction: null,
  propertyResearch: {},  // address → listing data
  returnDestination: 'home',   // 'home' | 'office' | 'custom' | 'none'
  returnCustomAddress: '',
  startAddress: '',
  directionsRenderer: null,
  mode: 'trip',           // 'trip' | 'showings'
  clientGroups: [],       // [{id, clientName, addresses, windowStart, windowEnd}]
};

// ── Utility ────────────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }
function $$(sel, ctx = document) { return Array.from(ctx.querySelectorAll(sel)); }

function showToast(title, message = '', type = 'info', duration = 4500) {
  const icons = { success: '✓', error: '✕', info: '○', warning: '!' };
  const container = $('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || '○'}</span>
    <div class="toast-body">
      <div class="toast-title">${title}</div>
      ${message ? `<div class="toast-message">${message}</div>` : ''}
    </div>
    <button class="toast-close" onclick="this.closest('.toast').remove()" title="Dismiss">×</button>
  `;
  container.appendChild(toast);
  // Errors stay until manually dismissed; everything else auto-hides
  if (type !== 'error') {
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(20px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
}

function showWebhookNotification(message) {
  const strip = $('webhook-strip');
  const msgEl = strip.querySelector('.webhook-message');
  if (msgEl) msgEl.textContent = message;
  strip.classList.add('visible');
  setTimeout(() => strip.classList.remove('visible'), 8000);
}

async function apiFetch(endpoint, options = {}) {
  const defaults = {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  };
  const opts = { ...defaults, ...options };
  if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
    opts.body = JSON.stringify(opts.body);
    opts.headers['Content-Type'] = 'application/json';
  }
  if (opts.body instanceof FormData) {
    delete opts.headers['Content-Type']; // Let browser set multipart boundary
  }

  const resp = await fetch(endpoint, opts);
  const data = await resp.json();
  return data;
}

function formatTime(timeStr) {
  if (!timeStr) return '—';
  return timeStr;
}

function sessionHash(session) {
  if (!session || !session.properties) return '';
  return session.properties.map(p => `${p.address}:${p.status}`).join('|');
}

// ── Screen navigation ──────────────────────────────────────────────────────────
function showScreen(name) {
  $$('.screen').forEach(s => s.classList.remove('active'));
  const target = $(`screen-${name}`);
  if (target) target.classList.add('active');
  AppState.currentScreen = name;

  // Update nav tab states
  $$('.nav-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.screen === name);
  });
}

// ── Status bar ─────────────────────────────────────────────────────────────────
function updateStatusBar() {
  const s = AppState.session;
  if (!s) return;

  const client = s.client || {};
  const props = s.properties || [];
  const confirmed = props.filter(p => p.status === 'confirmed').length;
  const declined = props.filter(p => p.status === 'declined').length;
  const pending = props.filter(p => !['confirmed', 'declined'].includes(p.status)).length;

  const bar = $('status-bar-stats');
  if (!bar) return;

  let html = '';
  if (s.session_date) {
    const d = new Date(s.session_date + 'T12:00:00');
    const dateStr = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    html += `<span class="status-pill session-date">📅 ${dateStr}</span>`;
  }
  if (client.name) {
    html += `<span class="status-pill client-name">👤 ${client.name}</span>`;
  }
  if (props.length > 0) {
    html += `<span class="status-pill count-confirmed">${confirmed} confirmed</span>`;
    if (declined > 0) html += `<span class="status-pill count-declined">${declined} declined</span>`;
    html += `<span class="status-pill count-pending">${pending} pending</span>`;
  }

  bar.innerHTML = html;
}

// ── Load session on startup ────────────────────────────────────────────────────
async function loadSession() {
  try {
    const data = await apiFetch('/api/session');
    if (data.status === 'success') {
      AppState.session = data.data;
      updateStatusBar();

      // Resume active session
      if (AppState.session.status !== 'idle' && AppState.session.properties?.length > 0) {
        // Restore addresses in the form
        const props = AppState.session.properties;
        AppState.addresses = props.map(p => p.address);
        renderAddressList();

        // Restore client
        if (AppState.session.client) {
          AppState.client = AppState.session.client;
          if (!AppState.session.client.not_found) {
            showClientCard(AppState.session.client);
          }
        }

        // Restore session date and time fields
        if (AppState.session.session_date) {
          const dateInput = $('session-date');
          if (dateInput) dateInput.value = AppState.session.session_date;
        }

        // If route has been calculated, go to status screen
        if (AppState.session.route) {
          AppState.route = AppState.session.route;
          showScreen('status');
          renderPropertyStatusCards();
        }

        showToast('Session resumed', `Client: ${AppState.session.client?.name || 'Unknown'}`, 'info');
      }
    }
  } catch (e) {
    console.warn('Could not load session:', e);
  }
}

// Load config (maps key, feature flags)
async function loadConfig() {
  try {
    const data = await apiFetch('/api/config');
    AppState.config = data;
    // Initialize Google Maps if key is available
    if (data.maps_key) {
      initGoogleMaps(data.maps_key);
    }
  } catch (e) {
    console.warn('Could not load config:', e);
  }
}

// ── Client lookup ──────────────────────────────────────────────────────────────
async function handleClientLookup(name) {
  if (!name.trim()) return;

  const btn = $('btn-lookup');
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  try {
    const result = await apiFetch('/api/client-lookup', {
      method: 'POST',
      body: { name }
    });

    if (result.status === 'success') {
      AppState.client = result.data;

      if (result.data.not_found) {
        showManualEntry(name);
        showToast('Client not found in CRM', 'Please fill in contact details manually.', 'warning');
      } else {
        showClientCard(result.data);
        showToast('Client found', `Loaded from ${result.data.crm_source?.toUpperCase() || 'CRM'}`, 'success');
      }
    } else {
      showToast('Lookup failed', result.error || 'Could not search CRM', 'error');
    }
  } catch (e) {
    showToast('Lookup error', e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

function showClientCard(client) {
  const card = $('client-confirm-card');
  $('manual-entry').style.display = 'none';

  $('client-display-name').textContent = client.name || '—';
  $('client-display-email').textContent = client.email || 'No email';
  $('client-display-phone').textContent = client.phone || 'No phone';
  $('client-display-source').textContent = (client.crm_source || 'manual').toUpperCase();

  card.classList.add('visible');
  $('client-manual-entry').classList.remove('visible');
}

function showManualEntry(prefillName = '') {
  $('client-confirm-card').classList.remove('visible');
  $('client-manual-entry').classList.add('visible');
  const nameInput = $('manual-client-name');
  if (nameInput && prefillName) nameInput.value = prefillName;
}

function saveManualClient() {
  const name = ($('manual-client-name')?.value || '').trim();
  const email = ($('manual-client-email')?.value || '').trim();
  const phone = ($('manual-client-phone')?.value || '').trim();

  if (!name) { showToast('Name required', 'Please enter the client name.', 'warning'); return; }

  AppState.client = { name, email, phone, crm_source: 'manual' };
  apiFetch('/api/session/update', { method: 'POST', body: { client: AppState.client } });
  showClientCard(AppState.client);
  showToast('Client saved', `${name} saved as manual entry.`, 'success');
}

// ── Address list management ────────────────────────────────────────────────────
function addAddressRow(address = '') {
  AppState.addresses.push(address);
  renderAddressList();
  // Focus the new input
  const inputs = $$('#address-list .address-row input');
  const last = inputs[inputs.length - 1];
  if (last) last.focus();
}

function removeAddressRow(index) {
  AppState.addresses.splice(index, 1);
  renderAddressList();
}

function renderAddressList() {
  const list = $('address-list');
  if (!list) return;
  list.innerHTML = '';

  AppState.addresses.forEach((addr, i) => {
    const row = document.createElement('div');
    row.className = 'address-row';
    row.innerHTML = `
      <span class="addr-num">${i + 1}</span>
      <input type="text" value="${addr}" placeholder="Full property address, City, MI" data-index="${i}">
      <button class="btn-remove-addr" title="Remove" data-index="${i}">×</button>
    `;
    list.appendChild(row);
  });

  // Bind events + attach Places autocomplete
  $$('#address-list input').forEach(input => {
    input.addEventListener('input', e => {
      AppState.addresses[parseInt(e.target.dataset.index)] = e.target.value;
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); addAddressRow(); }
    });
    attachAutocompleteWhenReady(input);
  });

  $$('#address-list .btn-remove-addr').forEach(btn => {
    btn.addEventListener('click', e => removeAddressRow(parseInt(e.target.dataset.index)));
  });
}

// ── Mode selector ──────────────────────────────────────────────────────────────
function initModeSelector() {
  $$('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => switchMode(btn.dataset.mode));
  });
}

function switchMode(mode) {
  AppState.mode = mode;

  // Update button active states
  $$('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });

  // Toggle section visibility
  const single = $('single-client-section');
  const multi  = $('multi-client-section');
  if (single) single.style.display = mode === 'trip'     ? '' : 'none';
  if (multi)  multi.style.display  = mode === 'showings' ? '' : 'none';

  // Seed one group if switching to showings and none exist
  if (mode === 'showings' && AppState.clientGroups.length === 0) {
    addClientGroup();
  }
}

// ── Client groups (Plan Showings mode) ─────────────────────────────────────────
let _groupIdCounter = 1;

function addClientGroup() {
  const id = _groupIdCounter++;
  AppState.clientGroups.push({
    id,
    clientName: '',
    addresses: [''],
    date: new Date().toISOString().split('T')[0],
    windowStart: '13:00',
    windowEnd: '18:00'
  });
  renderClientGroups();
  // Focus the new group's client name input after render
  setTimeout(() => {
    const input = $(`cg-client-${id}`);
    if (input) input.focus();
  }, 50);
}

function removeClientGroup(id) {
  if (AppState.clientGroups.length <= 1) {
    showToast('Cannot remove', 'At least one client group is required.', 'warning');
    return;
  }
  AppState.clientGroups = AppState.clientGroups.filter(g => g.id !== id);
  renderClientGroups();
}

function toggleGroupCollapse(id) {
  const card = $(`cg-card-${id}`);
  if (card) card.classList.toggle('collapsed');
}

function renderClientGroups() {
  const list = $('client-groups-list');
  if (!list) return;

  const groupColors = ['#C9A84C', '#4a9eff', '#4caf88', '#a78bfa'];

  list.innerHTML = AppState.clientGroups.map((group, gIdx) => {
    const badgeClass = `group-badge-${Math.min(gIdx + 1, 4)}`;
    const color = groupColors[gIdx % groupColors.length];
    const showRemove = AppState.clientGroups.length > 1;

    const addrRows = group.addresses.map((addr, aIdx) => `
      <div class="address-row" id="cg-addr-row-${group.id}-${aIdx}">
        <span class="addr-num">${aIdx + 1}</span>
        <input type="text" value="${addr}"
               placeholder="Full property address, City, MI"
               data-gid="${group.id}" data-aidx="${aIdx}"
               id="cg-addr-${group.id}-${aIdx}">
        <button class="btn-remove-addr" title="Remove"
                data-gid="${group.id}" data-aidx="${aIdx}">×</button>
      </div>
    `).join('');

    return `
      <div class="client-group-card" id="cg-card-${group.id}">
        <div class="client-group-header" onclick="toggleGroupCollapse(${group.id})">
          <div class="client-group-title">
            <span class="client-group-badge ${badgeClass}" style="color:${color};">
              Group ${gIdx + 1}
            </span>
            <span id="cg-title-label-${group.id}">
              ${group.clientName || 'New Client'}
            </span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            ${showRemove ? `<button class="client-group-remove-btn" onclick="event.stopPropagation();removeClientGroup(${group.id})">Remove</button>` : ''}
            <span class="client-group-collapse-icon">▾</span>
          </div>
        </div>

        <div class="client-group-body">
          <!-- Client lookup -->
          <div class="form-field">
            <label style="font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);">Client</label>
            <div class="client-group-lookup-row">
              <input type="text" id="cg-client-${group.id}"
                     value="${group.clientName}"
                     placeholder="Client name (e.g. Sarah Johnson)"
                     data-gid="${group.id}">
              <button class="btn btn-secondary btn-sm" onclick="handleGroupClientLookup(${group.id})">Search CRM</button>
            </div>
          </div>

          <!-- Time window -->
          <div>
            <label style="font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:var(--text-muted);display:block;margin-bottom:6px;">Availability Window</label>
            <div class="client-group-window">
              <div class="form-field" style="flex:1.2;">
                <label>Date</label>
                <input type="date" id="cg-date-${group.id}" value="${group.date}" data-gid="${group.id}">
              </div>
              <div class="form-field">
                <label>Start Time</label>
                <input type="time" id="cg-start-${group.id}" value="${group.windowStart}" data-gid="${group.id}">
              </div>
              <div class="form-field">
                <label>End Time</label>
                <input type="time" id="cg-end-${group.id}" value="${group.windowEnd}" data-gid="${group.id}">
              </div>
            </div>
          </div>

          <!-- Properties -->
          <div>
            <div class="client-group-addresses-header">
              <span>Properties</span>
              <button class="btn btn-ghost btn-sm" onclick="addGroupAddressRow(${group.id})">+ Add</button>
            </div>
            <div id="cg-addr-list-${group.id}">${addrRows}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // Bind events for all group inputs
  AppState.clientGroups.forEach(group => {
    // Client name input
    const clientInput = $(`cg-client-${group.id}`);
    if (clientInput) {
      clientInput.addEventListener('input', e => {
        group.clientName = e.target.value;
        const label = $(`cg-title-label-${group.id}`);
        if (label) label.textContent = e.target.value || 'New Client';
      });
    }

    // Time window inputs
    const dateInput = $(`cg-date-${group.id}`);
    if (dateInput) dateInput.addEventListener('change', e => { group.date = e.target.value; });

    const startInput = $(`cg-start-${group.id}`);
    if (startInput) startInput.addEventListener('change', e => { group.windowStart = e.target.value; });

    const endInput = $(`cg-end-${group.id}`);
    if (endInput) endInput.addEventListener('change', e => { group.windowEnd = e.target.value; });

    // Address inputs
    group.addresses.forEach((addr, aIdx) => {
      const addrInput = $(`cg-addr-${group.id}-${aIdx}`);
      if (addrInput) {
        addrInput.addEventListener('input', e => {
          group.addresses[aIdx] = e.target.value;
        });
        addrInput.addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); addGroupAddressRow(group.id); }
        });
        attachAutocompleteWhenReady(addrInput);
      }

      // Remove button
      const removeBtn = document.querySelector(`[data-gid="${group.id}"][data-aidx="${aIdx}"].btn-remove-addr`);
      if (removeBtn) {
        removeBtn.addEventListener('click', () => removeGroupAddressRow(group.id, aIdx));
      }
    });
  });
}

function addGroupAddressRow(groupId) {
  const group = AppState.clientGroups.find(g => g.id === groupId);
  if (!group) return;
  group.addresses.push('');
  renderClientGroups();
  // Focus new row
  setTimeout(() => {
    const inputs = $$(`#cg-addr-list-${groupId} input`);
    const last = inputs[inputs.length - 1];
    if (last) last.focus();
  }, 50);
}

function removeGroupAddressRow(groupId, aIdx) {
  const group = AppState.clientGroups.find(g => g.id === groupId);
  if (!group || group.addresses.length <= 1) return;
  group.addresses.splice(aIdx, 1);
  renderClientGroups();
}

async function handleGroupClientLookup(groupId) {
  const group = AppState.clientGroups.find(g => g.id === groupId);
  if (!group) return;
  const nameInput = $(`cg-client-${groupId}`);
  const name = nameInput?.value?.trim() || '';
  if (!name) {
    showToast('Enter a name', 'Type the client name before searching.', 'warning');
    return;
  }

  const btn = nameInput.nextElementSibling;
  const origText = btn?.innerHTML;
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>'; }

  try {
    const result = await apiFetch('/api/client-lookup', { method: 'POST', body: { name } });
    if (result.status === 'success' && !result.data.not_found) {
      group.clientName = result.data.name || name;
      group.clientEmail = result.data.email || '';
      group.clientPhone = result.data.phone || '';
      if (nameInput) nameInput.value = group.clientName;
      const label = $(`cg-title-label-${groupId}`);
      if (label) label.textContent = group.clientName;
      showToast('Client found', `Loaded from ${result.data.crm_source?.toUpperCase() || 'CRM'}`, 'success');
    } else {
      showToast('Not found', 'Client not found in CRM. Fill in details manually.', 'warning');
    }
  } catch (e) {
    showToast('Lookup error', e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = origText; }
  }
}

// ── Return destination ─────────────────────────────────────────────────────────
function resolveReturnAddress(startAddress) {
  switch (AppState.returnDestination) {
    case 'home':
      return AppState.config.default_start_address || startAddress;
    case 'office':
      return AppState.config.office_address || startAddress;
    case 'custom':
      return AppState.returnCustomAddress || null;
    case 'none':
    default:
      return null;
  }
}

function initReturnDestinationToggle() {
  $$('.return-destination-toggle button').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.return-destination-toggle button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      AppState.returnDestination = btn.dataset.return;
      const wrap = $('return-custom-wrap');
      if (wrap) wrap.style.display = AppState.returnDestination === 'custom' ? 'block' : 'none';
    });
  });
  const customInput = $('return-custom-address');
  if (customInput) {
    customInput.addEventListener('input', e => { AppState.returnCustomAddress = e.target.value; });
    attachAutocompleteWhenReady(customInput);
  }
}

// ── Route optimization ─────────────────────────────────────────────────────────
async function handleOptimizeRoute() {
  if (AppState.mode === 'showings') {
    await handleOptimizeMultiGroup();
    return;
  }

  // ── Single-client (Plan a Trip) mode ─────────────────────────────────────────
  const addresses = AppState.addresses.filter(a => a.trim());
  if (addresses.length === 0) {
    showToast('No addresses', 'Add at least one property address.', 'warning');
    return;
  }

  const sessionDate = $('session-date')?.value;
  const startTime = $('start-time')?.value || '13:00';
  const endTime = $('end-time')?.value || '18:00';
  const startAddress = $('start-address')?.value || AppState.config.default_start_address || 'Plainwell, MI';
  const maxMinutes = parseInt($('max-showing-minutes')?.value || '30');
  const direction = $$('.direction-toggle .active')[0]?.dataset.direction || 'start-loaded';
  const returnAddress = resolveReturnAddress(startAddress);

  if (!sessionDate) {
    showToast('Date required', 'Please select the showing day.', 'warning');
    return;
  }

  const sessionDatetime = `${sessionDate} ${startTime}`;
  if (new Date(sessionDatetime) < new Date()) {
    showToast('Date is in the past', 'Please select today or a future date and time.', 'error');
    return;
  }

  // Show plan before proceeding
  showPlan([
    `Optimizing route for ${addresses.length} propert${addresses.length > 1 ? 'ies' : 'y'}`,
    `Calling route_optimizer with Google Maps Distance Matrix API`,
    `Calculating shortest drive time using nearest-neighbor TSP`,
    `On failure: return mock route data so the session can continue`
  ]);

  const btn = $('btn-optimize');
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Optimizing...';

  try {
    const result = await apiFetch('/api/optimize-route', {
      method: 'POST',
      body: {
        addresses,
        start_address: startAddress,
        return_address: returnAddress,
        session_datetime: sessionDatetime,
        window_end_time: endTime,
        max_showing_minutes: maxMinutes,
        direction
      }
    });

    hidePlan();

    if (result.status === 'success') {
      AppState.route = result.data.route;
      AppState.startAddress = startAddress;
      AppState.session = (await apiFetch('/api/session')).data;
      updateStatusBar();

      if (result.data.mock) {
        showToast('Mock route loaded', 'Set GOOGLE_MAPS_API_KEY in .env for live travel times.', 'warning', 7000);
      } else {
        showToast('Route optimized', `${addresses.length} stops · ${result.data.total_duration_minutes} min total`, 'success');
      }

      if (result.data.warnings?.length > 0) {
        showToast('Schedule warning', result.data.warnings[0], 'warning', 8000);
      }

      renderRoute(result.data);
      showScreen('route');
    } else {
      showToast('Optimization failed', result.error || 'Unknown error', 'error');
    }
  } catch (e) {
    hidePlan();
    showToast('Network error', e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

async function handleOptimizeMultiGroup() {
  const groups = AppState.clientGroups;
  const sessionDate = $('session-date')?.value;
  const startAddress = $('start-address')?.value || AppState.config.default_start_address || 'Plainwell, MI';
  const maxMinutes = parseInt($('max-showing-minutes')?.value || '30');
  const direction = $$('.direction-toggle .active')[0]?.dataset.direction || 'start-loaded';

  if (!sessionDate) {
    showToast('Date required', 'Please select the showing day.', 'warning');
    return;
  }

  // Validate each group has at least one address
  for (const group of groups) {
    const addrs = group.addresses.filter(a => a.trim());
    if (addrs.length === 0) {
      showToast('Missing addresses', `Add at least one property for ${group.clientName || `Group ${groups.indexOf(group) + 1}`}.`, 'warning');
      return;
    }
  }

  showPlan([
    `Optimizing routes for ${groups.length} client group${groups.length > 1 ? 's' : ''}`,
    `Each group optimized independently via route_optimizer`,
    `Results displayed with color-coding per group in route sidebar`,
    `On failure: return mock data so the session can continue`
  ]);

  const btn = $('btn-optimize');
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Optimizing...';

  const groupResults = [];

  try {
    for (const group of groups) {
      const addrs = group.addresses.filter(a => a.trim());
      const groupDate = group.date || sessionDate;
      if (!groupDate) { showError(`Set a date for ${group.clientName || `Group ${group.id}`}`); return; }
      if (new Date(`${groupDate}T${group.windowStart || '13:00'}`) < new Date()) {
        showError(`Showing date for ${group.clientName || `Group ${group.id}`} is in the past`); return;
      }
      const sessionDatetime = `${groupDate} ${group.windowStart || '13:00'}`;
      const result = await apiFetch('/api/optimize-route', {
        method: 'POST',
        body: {
          addresses: addrs,
          start_address: startAddress,
          session_datetime: sessionDatetime,
          window_end_time: group.windowEnd || '18:00',
          max_showing_minutes: maxMinutes,
          direction
        }
      });

      if (result.status === 'success') {
        groupResults.push({
          groupId: group.id,
          clientName: group.clientName || `Group ${groups.indexOf(group) + 1}`,
          routeData: result.data
        });
        if (result.data.warnings?.length > 0) {
          showToast(
            `Schedule warning — ${group.clientName || 'Group ' + (groups.indexOf(group) + 1)}`,
            result.data.warnings[0], 'warning', 8000
          );
        }
      } else {
        showToast('Optimization failed', `${group.clientName || 'Group'}: ${result.error}`, 'error');
      }
    }

    hidePlan();

    if (groupResults.length === 0) {
      showToast('No results', 'All groups failed to optimize.', 'error');
      return;
    }

    // Flatten all stops into one route array, tagging each with groupIdx
    const flatRoute = [];
    groupResults.forEach((gr, gIdx) => {
      gr.routeData.route.forEach(stop => {
        flatRoute.push({ ...stop, _groupIdx: gIdx, _groupLabel: gr.clientName });
      });
    });

    AppState.route = flatRoute;
    AppState.startAddress = startAddress;
    AppState.multiGroupResults = groupResults;
    AppState.session = (await apiFetch('/api/session')).data;
    updateStatusBar();

    const totalStops = groupResults.reduce((s, gr) => s + gr.routeData.route.filter(r => !r.is_return).length, 0);
    showToast('Routes optimized', `${groups.length} groups · ${totalStops} total stops`, 'success');

    renderRouteMultiGroup(groupResults, startAddress);
    showScreen('route');

  } catch (e) {
    hidePlan();
    showToast('Network error', e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

// ── Auto-reschedule on cancellation ────────────────────────────────────────────
function promptAutoReschedule(address) {
  const remaining = (AppState.session?.properties || AppState.route || [])
    .filter(p => p.address !== address && !p.is_return && p.status !== 'declined');
  const n = remaining.length;

  if (n === 0) return; // nothing to reschedule

  showConfirmModal(
    'Showing Canceled — Reschedule?',
    `${address.split(',')[0]} was canceled. Compress the remaining ${n} showing${n !== 1 ? 's' : ''} to eliminate the gap?`,
    () => handleAutoReschedule(address)
  );
}

async function handleAutoReschedule(canceledAddress) {
  const sessionDate = AppState.session?.session_date;
  const startAddress = AppState.startAddress || AppState.config.default_start_address || 'Plainwell, MI';

  // Build remaining addresses from session properties, preserving original order
  const props = (AppState.session?.properties || []).filter(
    p => p.address !== canceledAddress && !p.is_return && p.status !== 'declined'
  );
  const remainingAddresses = props.map(p => p.address);

  if (remainingAddresses.length === 0) {
    showToast('No showings remaining', 'All showings have been removed or declined.', 'info');
    return;
  }

  // Re-use existing time window and direction from the original route
  const startTime = props[0]?.showing_start || '1:00 PM';
  // Parse "1:00 PM" → HH:MM for the API
  function parseTime12to24(t) {
    if (!t) return '13:00';
    const m = t.match(/(\d+):(\d+)\s*(AM|PM)/i);
    if (!m) return '13:00';
    let h = parseInt(m[1]);
    const min = m[2];
    const ampm = m[3].toUpperCase();
    if (ampm === 'PM' && h < 12) h += 12;
    if (ampm === 'AM' && h === 12) h = 0;
    return `${String(h).padStart(2,'0')}:${min}`;
  }

  const windowStart24 = sessionDate
    ? `${sessionDate} ${parseTime12to24(startTime)}`
    : `${new Date().toISOString().split('T')[0]} 13:00`;

  // Find window end from the last confirmed/pending stop's showing_end
  const lastProp = props[props.length - 1];
  const windowEnd24 = lastProp?.showing_end ? parseTime12to24(lastProp.showing_end) : '18:00';

  const maxMinutes = AppState.session?.max_showing_minutes || 30;
  const direction = $$('.direction-toggle .active')[0]?.dataset.direction || 'start-loaded';
  const returnAddress = resolveReturnAddress(startAddress);

  try {
    const result = await apiFetch('/api/optimize-route', {
      method: 'POST',
      body: {
        addresses: remainingAddresses,
        start_address: startAddress,
        return_address: returnAddress,
        session_datetime: windowStart24,
        window_end_time: windowEnd24,
        max_showing_minutes: maxMinutes,
        direction
      }
    });

    if (result.status !== 'success') {
      showToast('Reschedule failed', result.error || 'Unknown error', 'error');
      return;
    }

    const oldRoute = AppState.route || [];
    const newRoute = result.data.route;

    showReschedulePreviewModal(oldRoute, newRoute, async () => {
      // Apply: update session and re-render
      await apiFetch('/api/session/update', {
        method: 'POST',
        body: { route: newRoute }
      });
      AppState.route = newRoute;
      AppState.session = (await apiFetch('/api/session')).data;
      updateStatusBar();
      renderRoute(result.data);
      renderPropertyStatusCards();
      showToast('Schedule updated', `${remainingAddresses.length} showing${remainingAddresses.length !== 1 ? 's' : ''} rescheduled.`, 'success');
    });

  } catch (e) {
    showToast('Reschedule error', e.message, 'error');
  }
}

function showReschedulePreviewModal(oldRoute, newRoute, onApply) {
  const existing = $('reschedule-preview-modal');
  if (existing) existing.remove();

  // Build a map of old times by address
  const oldMap = {};
  (oldRoute || []).forEach(stop => {
    if (!stop.is_return) {
      oldMap[stop.address] = { start: stop.showing_start, end: stop.showing_end };
    }
  });

  const rows = (newRoute || []).filter(s => !s.is_return).map(stop => {
    const old = oldMap[stop.address];
    const changed = old && (old.start !== stop.showing_start || old.end !== stop.showing_end);
    const wasCell = old
      ? `<div class="reschedule-time-was">${old.start} – ${old.end}</div>`
      : `<div class="reschedule-time-unchanged">—</div>`;
    const nowCell = changed
      ? `<div class="reschedule-time-now">${stop.showing_start} – ${stop.showing_end} <span class="reschedule-badge-changed">changed</span></div>`
      : `<div class="reschedule-time-unchanged">${stop.showing_start} – ${stop.showing_end}</div>`;
    return `
      <tr>
        <td class="reschedule-addr">${stop.address.split(',')[0]}</td>
        <td>${wasCell}</td>
        <td>${nowCell}</td>
      </tr>
    `;
  }).join('');

  const modal = document.createElement('div');
  modal.id = 'reschedule-preview-modal';
  modal.className = 'modal-overlay';
  modal.style.display = 'flex';
  modal.innerHTML = `
    <div class="modal-box" style="max-width:560px;width:100%;">
      <h3 style="margin-bottom:4px;">Reschedule Preview</h3>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:4px;">
        Review the updated times before applying. Changes are highlighted in gold.
      </p>
      <table class="reschedule-table">
        <thead>
          <tr>
            <th>Property</th>
            <th>Was</th>
            <th>Now</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="modal-actions" style="margin-top:8px;">
        <button class="btn btn-secondary" id="btn-reschedule-keep">Keep Current Times</button>
        <button class="btn btn-primary" id="btn-reschedule-apply">Apply Changes</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  $('btn-reschedule-keep').addEventListener('click', () => modal.remove());
  $('btn-reschedule-apply').addEventListener('click', () => {
    modal.remove();
    onApply();
  });
}

function showConfirmModal(title, message, onConfirm) {
  const modal = $('confirm-modal');
  const titleEl = $('modal-title');
  const msgEl = $('modal-message');
  const confirmBtn = $('btn-confirm-modal');

  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;
  if (modal) modal.classList.add('visible');

  // Remove old listener by cloning the button
  const newConfirmBtn = confirmBtn.cloneNode(true);
  confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
  newConfirmBtn.addEventListener('click', () => {
    modal.classList.remove('visible');
    onConfirm();
  });
}

// ── Route rendering ────────────────────────────────────────────────────────────
function renderRouteMultiGroup(groupResults, startAddress) {
  const sidebar = $('route-stops-list');
  if (!sidebar) return;

  clearMapMarkers();

  const groupColors = ['#C9A84C', '#4a9eff', '#4caf88', '#a78bfa'];

  // Warning banner
  const warningBanner = $('route-warning-banner');
  if (warningBanner) warningBanner.style.display = 'none';

  // Route stats
  const totalStops = groupResults.reduce((s, gr) => s + gr.routeData.route.filter(r => !r.is_return).length, 0);
  const totalMin = groupResults.reduce((s, gr) => s + (gr.routeData.total_duration_minutes || 0), 0);
  const statsEl = $('route-total-duration');
  if (statsEl) statsEl.textContent = `${totalStops} stops · ${totalMin} min total`;

  // Color legend at top
  const legendItems = groupResults.map((gr, gIdx) => `
    <div class="route-group-legend-item">
      <div class="route-group-legend-dot" style="background:${groupColors[gIdx % groupColors.length]};"></div>
      <span>${gr.clientName}</span>
    </div>
  `).join('');

  const startCard = startAddress ? `
    <div class="route-stop-card route-stop-start">
      <div class="route-stop-header">
        <div class="stop-number" style="background:#4a9eff;font-size:13px;font-weight:800;">S</div>
        <div class="stop-address">${startAddress}</div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);padding:2px 0 0 36px;">Starting location</div>
    </div>` : '';

  let stopsHtml = '';
  groupResults.forEach((gr, gIdx) => {
    const color = groupColors[gIdx % groupColors.length];
    stopsHtml += `
      <div class="route-group-divider">
        <div class="route-group-divider-line"></div>
        <div class="route-group-divider-label" style="background:${color}20;color:${color};border:1px solid ${color}40;">
          ${gr.clientName}
        </div>
        <div class="route-group-divider-line"></div>
      </div>
    `;

    gr.routeData.route.forEach(stop => {
      if (stop.is_return) {
        stopsHtml += `
          <div class="route-stop-card route-stop-return" style="border-left:3px solid ${color};">
            <div class="route-stop-header">
              <div class="stop-number" style="background:var(--text-muted);font-size:14px;">🏠</div>
              <div class="stop-address">${stop.address}</div>
            </div>
            <div class="stop-times">
              <div class="stop-time-item">
                <div class="stop-time-label">Arrive</div>
                <div class="stop-time-value">${formatTime(stop.arrival_time)}</div>
              </div>
            </div>
          </div>`;
      } else {
        stopsHtml += `
          <div class="route-stop-card" data-order="${stop.order}" style="border-left:3px solid ${color};">
            <div class="route-stop-header">
              <div class="stop-number" style="background:${color};color:#0D1B2A;">${stop.order}</div>
              <div class="stop-address">${stop.address}</div>
            </div>
            <div class="stop-times">
              <div class="stop-time-item">
                <div class="stop-time-label">Arrive</div>
                <div class="stop-time-value">${formatTime(stop.arrival_time)}</div>
              </div>
              <div class="stop-time-item">
                <div class="stop-time-label">Showing</div>
                <div class="stop-time-value">${formatTime(stop.showing_start)} – ${formatTime(stop.showing_end)}</div>
              </div>
            </div>
            ${stop.travel_to_next_minutes ? `
              <div class="stop-travel-next">
                <span>🚗</span>
                <span>${stop.travel_to_next_minutes} min to next stop</span>
              </div>
            ` : ''}
          </div>`;
      }
    });
  });

  sidebar.innerHTML = `
    <div class="route-group-legend">${legendItems}</div>
    ${startCard}
    ${stopsHtml}
  `;

  // Map: show all stops — use first group's route for directions
  if (AppState.map && groupResults.length > 0) {
    initRouteOnMap(groupResults[0].routeData.route);
  } else if (!AppState.config.maps_key) {
    renderMapPlaceholder(totalStops);
  }
}

function renderRoute(routeData) {
  const { route, total_duration_minutes, fits_window } = routeData;
  const sidebar = $('route-stops-list');
  if (!sidebar) return;

  // Clear old markers
  clearMapMarkers();

  // Warning banner
  const warningBanner = $('route-warning-banner');
  if (!fits_window && warningBanner) {
    warningBanner.style.display = 'block';
    warningBanner.textContent = `Schedule is tight (${total_duration_minutes} min). Consider removing a stop or shortening showing time.`;
  } else if (warningBanner) {
    warningBanner.style.display = 'none';
  }

  // Route stats
  const statsEl = $('route-total-duration');
  if (statsEl) statsEl.textContent = `${total_duration_minutes} min total`;

  // Sidebar stops — prepend Start card
  const startCard = AppState.startAddress ? `
    <div class="route-stop-card route-stop-start">
      <div class="route-stop-header">
        <div class="stop-number" style="background:#4a9eff;font-size:13px;font-weight:800;">S</div>
        <div class="stop-address">${AppState.startAddress}</div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);padding:2px 0 0 36px;">Starting location</div>
    </div>` : '';

  sidebar.innerHTML = startCard + route.map(stop => {
    if (stop.is_return) {
      return `
        <div class="route-stop-card route-stop-return">
          <div class="route-stop-header">
            <div class="stop-number" style="background:var(--text-muted);font-size:14px;">🏠</div>
            <div class="stop-address">${stop.address}</div>
          </div>
          <div class="stop-times">
            <div class="stop-time-item">
              <div class="stop-time-label">Arrive</div>
              <div class="stop-time-value">${formatTime(stop.arrival_time)}</div>
            </div>
          </div>
        </div>`;
    }
    return `
    <div class="route-stop-card" data-order="${stop.order}">
      <div class="route-stop-header">
        <div class="stop-number">${stop.order}</div>
        <div class="stop-address">${stop.address}</div>
      </div>
      <div class="stop-times">
        <div class="stop-time-item">
          <div class="stop-time-label">Arrive</div>
          <div class="stop-time-value">${formatTime(stop.arrival_time)}</div>
        </div>
        <div class="stop-time-item">
          <div class="stop-time-label">Showing</div>
          <div class="stop-time-value">${formatTime(stop.showing_start)} – ${formatTime(stop.showing_end)}</div>
        </div>
      </div>
      ${stop.travel_to_next_minutes ? `
        <div class="stop-travel-next">
          <span>🚗</span>
          <span>${stop.travel_to_next_minutes} min to next stop</span>
        </div>
      ` : ''}
    </div>`;
  }).join('');

  // Initialize/update Google Map.
  // If AppState.map exists → render immediately.
  // If Maps SDK is loading (key present, map not yet ready) → onGoogleMapsReady will
  // call initRouteOnMap once the SDK fires, because AppState.route is already set.
  // If no key → show placeholder.
  if (AppState.map) {
    initRouteOnMap(route);
  } else if (!AppState.config.maps_key) {
    renderMapPlaceholder(route.length);
  }
  // else: SDK is loading — onGoogleMapsReady will pick up AppState.route automatically
}

function renderMapPlaceholder(stopCount) {
  const mapDiv = $('map');
  if (!mapDiv) return;
  mapDiv.innerHTML = `
    <div class="map-placeholder">
      <div class="map-icon">🗺</div>
      <div style="font-size:14px;color:#8fa4bc;">Route: ${stopCount} stop${stopCount > 1 ? 's' : ''} planned</div>
      <div style="font-size:12px;color:#6b7c93;margin-top:4px;">Set GOOGLE_MAPS_API_KEY in .env to enable live map</div>
      <div style="margin-top:16px;display:flex;flex-direction:column;gap:4px;text-align:left;">
        ${(AppState.route || []).map((stop, i) => `
          <div style="font-size:12px;color:#bccfe0;display:flex;gap:8px;align-items:center;">
            <span style="background:#c9a84c;color:#0d1b2a;width:20px;height:20px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;flex-shrink:0;">${i+1}</span>
            ${stop.address}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

// ── Google Maps integration ────────────────────────────────────────────────────
function initGoogleMaps(apiKey) {
  if (window.google?.maps) return; // Already loaded

  const script = document.createElement('script');
  // Load Places library alongside Maps; callback triggers autocomplete setup
  script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places,directions&callback=initGoogleMapsAutocomplete`;
  script.async = true;
  script.defer = true;
  document.head.appendChild(script);
}

// Attach a Places Autocomplete instance to a single input, biased to US addresses.
function attachAutocomplete(input) {
  if (!window.google?.maps?.places) return;
  if (input.dataset.autocompleteAttached) return;
  input.dataset.autocompleteAttached = 'true';

  const ac = new google.maps.places.Autocomplete(input, {
    types: ['address'],
    componentRestrictions: { country: 'us' },
    fields: ['formatted_address']
  });

  ac.addListener('place_changed', () => {
    const place = ac.getPlace();
    if (place?.formatted_address) {
      input.value = place.formatted_address;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    // Dismiss the dropdown
    input.blur();
    setTimeout(() => input.focus(), 0);
  });
}

// Queue autocomplete attachment if Maps SDK isn't loaded yet.
function attachAutocompleteWhenReady(input) {
  if (window._googleMapsReady) {
    attachAutocomplete(input);
  } else {
    window._pendingAutocompleteInputs = window._pendingAutocompleteInputs || [];
    window._pendingAutocompleteInputs.push(input);
  }
}

// Called by the Maps SDK callback (defined in index.html) after Places loads.
// Also initializes the map so the old onGoogleMapsReady logic still runs.
window._googleMapsReady = false;

window.onGoogleMapsReady = function() {
  const mapDiv = $('map');
  if (!mapDiv) return;

  AppState.map = new google.maps.Map(mapDiv, {
    zoom: 10,
    center: { lat: 42.6328, lng: -85.6512 }, // Plainwell, MI
    mapTypeId: 'roadmap',
    styles: [
      { elementType: 'geometry', stylers: [{ color: '#1a2d42' }] },
      { elementType: 'labels.text.fill', stylers: [{ color: '#8fa4bc' }] },
      { elementType: 'labels.text.stroke', stylers: [{ color: '#0d1b2a' }] },
      { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#243b55' }] },
      { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#243b55' }] },
      { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0d1b2a' }] },
      { featureType: 'poi', stylers: [{ visibility: 'off' }] }
    ]
  });

  // If route is already loaded, render it
  if (AppState.route) {
    initRouteOnMap(AppState.route);
  }
};

function clearMapMarkers() {
  AppState.mapMarkers.forEach(m => m.setMap(null));
  AppState.mapMarkers = [];
  if (AppState.mapPolyline) {
    AppState.mapPolyline.setMap(null);
    AppState.mapPolyline = null;
  }
}

function initRouteOnMap(route) {
  if (!AppState.map || !window.google) return;
  clearMapMarkers();

  // Clear previous directions renderer
  if (AppState.directionsRenderer) {
    AppState.directionsRenderer.setMap(null);
    AppState.directionsRenderer = null;
  }

  // Filter out the return stop for routing purposes; handle it separately
  const showingStops = route.filter(s => !s.is_return);
  if (showingStops.length === 0) return;

  const origin = AppState.startAddress || showingStops[0].address;
  const returnStop = route.find(s => s.is_return);
  const destination = returnStop ? returnStop.address : showingStops[showingStops.length - 1].address;

  // Build waypoints from all showing stops (origin→stop1→...→stopN→destination)
  // If no return, destination is last stop so waypoints are everything in between
  const waypointStops = returnStop ? showingStops : showingStops.slice(0, -1);
  const waypoints = waypointStops.map(s => ({
    location: s.address,
    stopover: true
  }));

  const directionsService = new google.maps.DirectionsService();
  const renderer = new google.maps.DirectionsRenderer({
    map: AppState.map,
    suppressMarkers: true,   // we draw our own numbered markers below
    polylineOptions: {
      strokeColor: '#C9A84C',
      strokeOpacity: 0.8,
      strokeWeight: 4
    }
  });
  AppState.directionsRenderer = renderer;

  directionsService.route({
    origin,
    destination,
    waypoints,
    travelMode: google.maps.TravelMode.DRIVING,
    optimizeWaypoints: false   // order already optimized by backend
  }, (result, status) => {
    if (status === 'OK') {
      renderer.setDirections(result);
    } else {
      console.warn('[map] Directions API failed:', status, '— falling back to geocode markers');
    }

    // Always place custom markers regardless of directions result
    placeRouteMarkers(route, origin, returnStop);
  });
}

function placeRouteMarkers(route, origin, returnStop) {
  const geocoder = new google.maps.Geocoder();
  const bounds = new google.maps.LatLngBounds();

  // Start marker (blue "S")
  geocoder.geocode({ address: origin }, (results, status) => {
    if (status !== 'OK') return;
    const pos = results[0].geometry.location;
    bounds.extend(pos);
    const marker = new google.maps.Marker({
      position: pos,
      map: AppState.map,
      label: { text: 'S', color: '#ffffff', fontWeight: 'bold', fontSize: '12px' },
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 16,
              fillColor: '#4a9eff', fillOpacity: 1, strokeColor: '#0D1B2A', strokeWeight: 2 },
      title: `Start: ${origin}`
    });
    AppState.mapMarkers.push(marker);
  });

  // Numbered stop markers (gold)
  route.filter(s => !s.is_return).forEach(stop => {
    geocoder.geocode({ address: stop.address }, (results, status) => {
      if (status !== 'OK') return;
      const pos = results[0].geometry.location;
      bounds.extend(pos);
      const marker = new google.maps.Marker({
        position: pos,
        map: AppState.map,
        label: { text: String(stop.order), color: '#0D1B2A', fontWeight: 'bold', fontSize: '12px' },
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: 16,
                fillColor: '#C9A84C', fillOpacity: 1, strokeColor: '#0D1B2A', strokeWeight: 2 },
        title: `${stop.order}. ${stop.address}\n${stop.showing_start} – ${stop.showing_end}`
      });
      AppState.mapMarkers.push(marker);
      AppState.map.fitBounds(bounds, { padding: 60 });
    });
  });

  // Return marker (house icon, gray)
  if (returnStop) {
    geocoder.geocode({ address: returnStop.address }, (results, status) => {
      if (status !== 'OK') return;
      const pos = results[0].geometry.location;
      bounds.extend(pos);
      const marker = new google.maps.Marker({
        position: pos,
        map: AppState.map,
        label: { text: '🏠', color: '#ffffff', fontSize: '13px' },
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: 16,
                fillColor: '#6b7c93', fillOpacity: 1, strokeColor: '#0D1B2A', strokeWeight: 2 },
        title: `Return: ${returnStop.address}`
      });
      AppState.mapMarkers.push(marker);
      AppState.map.fitBounds(bounds, { padding: 60 });
    });
  }
}

// ── Calendar ───────────────────────────────────────────────────────────────────
function buildGoogleCalendarUrl(title, startStr, endStr, location, description) {
  // startStr / endStr: "1:00 PM" style — need to combine with session date
  const session = AppState.session || {};
  const dateStr = session.session_date || new Date().toISOString().split('T')[0];

  function parseToGCal(timeStr, date) {
    if (!timeStr) return '';
    const d = new Date(`${date} ${timeStr}`);
    if (isNaN(d)) return '';
    // Format: YYYYMMDDTHHmmss (local time, no Z)
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}00`;
  }

  const start = parseToGCal(startStr, dateStr);
  const end = parseToGCal(endStr, dateStr) || start.replace(/T\d{6}$/, m => {
    // Add 30 min if no end
    const t = parseInt(m.slice(1,3))*60 + parseInt(m.slice(3,5)) + 30;
    return `T${String(Math.floor(t/60)%24).padStart(2,'0')}${String(t%60).padStart(2,'0')}00`;
  });

  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: title,
    dates: `${start}/${end}`,
    location: location || '',
    details: description || '',
    trp: 'true'  // show as tentative
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

async function handleAddToCalendar() {
  const session = AppState.session || {};
  const route = AppState.route || session.route || [];
  const showingStops = route.filter(s => !s.is_return);
  const returnStop = route.find(s => s.is_return);

  if (showingStops.length === 0) {
    showToast('No route', 'Optimize a route first.', 'warning');
    return;
  }

  const clientName = session.client?.name || AppState.client?.name || 'Client';
  const firstStop = showingStops[0];
  const lastStop  = showingStops[showingStops.length - 1];

  // Full trip block: departs at first showing arrival, ends at return arrival (or last showing end)
  const tripStart = firstStop.arrival_time;
  const tripEnd   = returnStop ? returnStop.arrival_time : lastStop.showing_end;
  const allAddresses = showingStops.map(s => s.address.split(',')[0]).join(' → ');
  const tripDescription =
    `Showing day for ${clientName}\n` +
    `Route: ${AppState.startAddress || 'Home'} → ${allAddresses}` +
    (returnStop ? ` → ${returnStop.address.split(',')[0]}` : '') + '\n\n' +
    showingStops.map(s => `• ${s.address.split(',')[0]}: ${s.showing_start} – ${s.showing_end}`).join('\n');

  const fullTripUrl = buildGoogleCalendarUrl(
    `🏠 Showing Day — ${clientName} (${showingStops.length} properties)`,
    tripStart, tripEnd,
    firstStop.address,
    tripDescription
  );

  // Individual showing events
  const individualUrls = showingStops.map(stop => ({
    address: stop.address,
    time: `${stop.showing_start} – ${stop.showing_end}`,
    url: buildGoogleCalendarUrl(
      `🏠 Showing: ${stop.address.split(',')[0]}`,
      stop.showing_start,
      stop.showing_end,
      stop.address,
      `Showing for ${clientName}\nAddress: ${stop.address}\nArrival: ${stop.arrival_time}`
    )
  }));

  showCalendarLinksModal({ fullTripUrl, individualUrls, clientName, tripStart, tripEnd, showingStops });
  showScreen('status');
  renderPropertyStatusCards();
}

function showCalendarLinksModal({ fullTripUrl, individualUrls, clientName, tripStart, tripEnd, showingStops }) {
  const existing = $('cal-links-modal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'cal-links-modal';
  modal.className = 'modal-overlay';
  modal.style.display = 'flex';
  modal.innerHTML = `
    <div class="modal-box" style="max-width:560px;width:100%;">
      <h3 style="margin-bottom:4px;">Add to Google Calendar</h3>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px;">
        Choose how to block your calendar. Each link opens Google Calendar pre-filled and ready to save.
      </p>

      <!-- Full trip block -->
      <div style="margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:var(--gold);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px;">Full Trip Block</div>
        <a href="${fullTripUrl}" target="_blank" rel="noopener"
           style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:rgba(201,168,76,0.08);border:1px solid rgba(201,168,76,0.3);border-radius:10px;text-decoration:none;color:inherit;transition:background 0.2s;"
           onmouseover="this.style.background='rgba(201,168,76,0.15)'" onmouseout="this.style.background='rgba(201,168,76,0.08)'">
          <span style="font-size:22px;">📅</span>
          <div style="flex:1;">
            <div style="font-weight:600;font-size:14px;color:var(--white);">Showing Day — ${clientName}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${tripStart} – ${tripEnd} · ${showingStops.length} properties · Single calendar block</div>
          </div>
          <span style="font-size:12px;color:var(--gold);font-weight:600;">Add →</span>
        </a>
      </div>

      <!-- Individual showings -->
      <div>
        <div style="font-size:11px;font-weight:700;color:var(--gold);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px;">Individual Showings</div>
        <div style="display:flex;flex-direction:column;gap:8px;">
          ${individualUrls.map((item, i) => `
            <a href="${item.url}" target="_blank" rel="noopener"
               style="display:flex;align-items:center;gap:10px;padding:11px 14px;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;text-decoration:none;color:inherit;transition:background 0.2s;"
               onmouseover="this.style.background='rgba(255,255,255,0.07)'" onmouseout="this.style.background='rgba(255,255,255,0.03)'">
              <span style="background:var(--gold);color:var(--navy);width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;flex-shrink:0;">${i+1}</span>
              <div style="flex:1;">
                <div style="font-size:13px;color:var(--white);">${item.address.split(',')[0]}</div>
                <div style="font-size:11px;color:var(--text-muted);">${item.time}</div>
              </div>
              <span style="font-size:11px;color:var(--gold);">Add →</span>
            </a>
          `).join('')}
        </div>
      </div>

      <div class="modal-actions" style="margin-top:24px;">
        <button class="btn btn-primary" onclick="document.getElementById('cal-links-modal').remove()">Done</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

// ── Property status panel ──────────────────────────────────────────────────────
function renderPropertyStatusCards() {
  const container = $('property-cards-container');
  if (!container) return;

  const session = AppState.session;
  const props = session?.properties || AppState.route || [];
  if (props.length === 0) {
    container.innerHTML = '<div class="text-muted text-sm" style="text-align:center;padding:40px;">No properties yet — optimize a route first.</div>';
    return;
  }

  container.innerHTML = props.map((prop, idx) => {
    const addr = prop.address;
    const status = prop.status || 'pending';
    const showStart = prop.showing_start || '';
    const showEnd = prop.showing_end || '';
    const order = prop.order || idx + 1;
    const mls = prop.mls_number || '';

    return `
    <div class="property-card" id="prop-card-${idx}" data-address="${addr}">
      <div class="property-card-header" onclick="togglePropertyCard(${idx})">
        <div class="prop-order">${order}</div>
        <div class="prop-info">
          <div class="prop-address">${addr}</div>
          <div class="prop-time">${showStart} – ${showEnd}</div>
        </div>
        <div class="prop-status">
          <span class="badge badge-${status}" id="status-badge-${idx}">${statusLabel(status)}</span>
        </div>
      </div>
      <div class="property-card-body" id="prop-body-${idx}">
        <!-- Status actions -->
        <div class="property-card-actions">
          <span class="action-label">Status:</span>
          <button class="btn btn-sm btn-secondary" onclick="updatePropertyStatus('${addr}', 'requested', ${idx})">Requested</button>
          <button class="btn btn-sm btn-success" onclick="updatePropertyStatus('${addr}', 'confirmed', ${idx})">Confirmed</button>
          <button class="btn btn-sm btn-danger" onclick="updatePropertyStatus('${addr}', 'declined', ${idx})">Declined</button>
        </div>

        <!-- ShowingTime request block -->
        <div class="showingtime-checklist">
          <div class="checklist-label">ShowingTime Request Block</div>
          <div class="checklist-block" id="checklist-${idx}"><pre style="white-space:pre-wrap;font-size:11px;color:#bccfe0;">═══════════════════════════════════════
   SHOWINGTIME REQUEST
═══════════════════════════════════════
Address:      ${addr}
MLS Number:   ${mls || 'Unknown — check listing'}
Date:         ${session?.session_date || '—'}
Time Window:  ${showStart} – ${showEnd}
Agent Name:   Jason O'Brien
Agent Phone:  (check your ShowingTime profile)
═══════════════════════════════════════
Submit at showingtime.com or the mobile app</pre></div>
          <button class="btn btn-sm btn-ghost mt-8" onclick="copyToClipboard('checklist-${idx}')">📋 Copy</button>
        </div>

        <!-- Property research -->
        <div class="property-research" id="research-${idx}">
          <div id="research-content-${idx}">
            <button class="btn btn-sm btn-secondary" onclick="loadPropertyResearch('${addr}', ${idx})">
              Load Property Data
            </button>
          </div>
          <!-- Disclosure upload -->
          <div class="disclosure-upload mt-16" id="upload-area-${idx}"
               onclick="$('disclosure-file-${idx}').click()"
               ondragover="handleDragOver(event, ${idx})"
               ondragleave="handleDragLeave(event, ${idx})"
               ondrop="handleDisclosureDrop(event, '${addr}', ${idx})">
            <div class="upload-icon">📄</div>
            <div class="upload-text">Drop Disclosure PDF here</div>
            <div class="upload-hint">or click to browse</div>
            <input type="file" id="disclosure-file-${idx}" accept=".pdf" onchange="handleDisclosureUpload(event, '${addr}', ${idx})">
          </div>
          <div id="red-flag-report-${idx}"></div>
        </div>
      </div>
    </div>
    `;
  }).join('');
}

function togglePropertyCard(idx) {
  const body = $(`prop-body-${idx}`);
  if (body) body.classList.toggle('expanded');
}

function statusLabel(status) {
  const labels = {
    pending: '⚪ Pending',
    requested: '🟣 Requested',
    tentative: '🟡 Tentative',
    confirmed: '🟢 Confirmed',
    declined: '🔴 Declined',
    'auto-updated': '🔄 Auto-Updated'
  };
  return labels[status] || status;
}

async function updatePropertyStatus(address, status, idx) {
  try {
    const result = await apiFetch('/api/property/status', {
      method: 'POST',
      body: { address, status }
    });

    if (result.status === 'success') {
      // Update badge
      const badge = $(`status-badge-${idx}`);
      if (badge) {
        badge.className = `badge badge-${status}`;
        badge.textContent = statusLabel(status);
      }

      // Reload session
      AppState.session = (await apiFetch('/api/session')).data;
      updateStatusBar();

      showToast(`Status updated`, `${address.split(',')[0]} → ${status}`, 'success');

      // If confirmed, auto-load property research
      if (status === 'confirmed') {
        loadPropertyResearch(address, idx);
      }

      // If declined, prompt calendar deletion then auto-reschedule
      if (status === 'declined') {
        const prop = AppState.session?.properties?.find(p => p.address === address);
        if (prop?.calendar_event_id) {
          if (confirm(`Delete calendar event for ${address.split(',')[0]}?`)) {
            await apiFetch('/api/calendar/delete', {
              method: 'POST',
              body: { event_id: prop.calendar_event_id, address }
            });
          }
        }
        // Prompt auto-reschedule after a short delay so the UI settles
        setTimeout(() => promptAutoReschedule(address), 300);
      }
    } else {
      showToast('Update failed', result.error || 'Unknown error', 'error');
    }
  } catch (e) {
    showToast('Error', e.message, 'error');
  }
}

// ── Property research ──────────────────────────────────────────────────────────
async function loadPropertyResearch(address, idx) {
  const contentDiv = $(`research-content-${idx}`);
  if (!contentDiv) return;

  contentDiv.innerHTML = '<div class="loading">Loading property data... <span class="spinner"></span></div>';

  try {
    const result = await apiFetch('/api/property-research', {
      method: 'POST',
      body: { address }
    });

    if (result.status === 'success') {
      const d = result.data;
      AppState.propertyResearch[address] = d;
      contentDiv.innerHTML = renderPropertyResearchHTML(d);
      showToast('Property data loaded', `${address.split(',')[0]}`, 'success');
    } else {
      contentDiv.innerHTML = `<div class="text-muted text-sm">Data unavailable — ${result.error || 'could not fetch listing'}</div>`;
    }
  } catch (e) {
    contentDiv.innerHTML = `<div class="text-muted text-sm">Error loading data: ${e.message}</div>`;
  }
}

function renderPropertyResearchHTML(d) {
  if (!d) return '<div class="text-muted text-sm">No data</div>';
  const stats = [
    { label: 'Price', value: d.price || '—' },
    { label: 'Beds', value: d.beds || '—' },
    { label: 'Baths', value: d.baths || '—' },
    { label: 'Sqft', value: d.sqft ? Number(d.sqft).toLocaleString() : '—' },
    { label: 'Year Built', value: d.year_built || '—' },
    { label: 'Days on Mkt', value: d.days_on_market || '—' },
    { label: 'Taxes', value: d.tax_estimate || '—' },
    { label: 'Zestimate', value: d.zestimate || '—' }
  ];

  return `
    <div class="property-stats">
      ${stats.map(s => `
        <div class="property-stat">
          <div class="stat-label">${s.label}</div>
          <div class="stat-value">${s.value}</div>
        </div>
      `).join('')}
    </div>
    ${d.school_district ? `<div class="text-muted text-sm" style="margin-bottom:8px;">School District: ${d.school_district}</div>` : ''}
    ${d.description ? `<div class="property-description">${d.description.slice(0, 350)}${d.description.length > 350 ? '...' : ''}</div>` : ''}
    ${d.data_source === 'mock' ? '<div class="text-xs text-muted" style="margin-top:4px;font-style:italic;">Mock data — implement Zillow scraper for live listing data</div>' : ''}
  `;
}

// ── Disclosure upload ──────────────────────────────────────────────────────────
function handleDragOver(event, idx) {
  event.preventDefault();
  $(`upload-area-${idx}`)?.classList.add('dragover');
}

function handleDragLeave(event, idx) {
  $(`upload-area-${idx}`)?.classList.remove('dragover');
}

function handleDisclosureDrop(event, address, idx) {
  event.preventDefault();
  $(`upload-area-${idx}`)?.classList.remove('dragover');
  const file = event.dataTransfer?.files?.[0];
  if (file?.type === 'application/pdf') {
    uploadDisclosure(file, address, idx);
  } else {
    showToast('PDF only', 'Please drop a PDF file.', 'warning');
  }
}

function handleDisclosureUpload(event, address, idx) {
  const file = event.target.files?.[0];
  if (file) uploadDisclosure(file, address, idx);
}

async function uploadDisclosure(file, address, idx) {
  const uploadArea = $(`upload-area-${idx}`);
  const reportDiv = $(`red-flag-report-${idx}`);

  if (uploadArea) {
    uploadArea.innerHTML = `
      <div class="upload-icon"><span class="spinner"></span></div>
      <div class="upload-text">Analyzing disclosure with Claude AI...</div>
    `;
  }

  try {
    const formData = new FormData();
    formData.append('pdf', file);
    formData.append('address', address);

    const result = await apiFetch('/api/analyze-disclosure', {
      method: 'POST',
      body: formData
    });

    if (result.status === 'success') {
      const data = result.data;
      if (uploadArea) {
        uploadArea.innerHTML = `<div class="upload-text" style="color:#27c17c;">PDF analyzed: ${file.name}</div>`;
      }
      if (reportDiv) {
        reportDiv.innerHTML = renderRedFlagReport(data);
      }
      showToast('Disclosure analyzed', `${data.red_flags?.length || 0} red flag(s) found`, 'success');
    } else {
      if (uploadArea) uploadArea.innerHTML = `<div class="upload-text" style="color:#e05555;">Analysis failed: ${result.error}</div>`;
      showToast('Analysis failed', result.error || 'Unknown error', 'error');
    }
  } catch (e) {
    if (uploadArea) uploadArea.innerHTML = `<div class="upload-text" style="color:#e05555;">Error: ${e.message}</div>`;
    showToast('Upload error', e.message, 'error');
  }
}

function renderRedFlagReport(data) {
  if (!data || !data.red_flags) return '';
  const flags = data.red_flags;
  if (flags.length === 0) {
    return `<div class="text-sm" style="color:#27c17c;padding:8px 0;">No significant red flags found in this disclosure.</div>`;
  }

  return `
    <div class="red-flag-report">
      <div class="report-header">Disclosure Red Flags — ${data.summary || ''}</div>
      ${flags.map(flag => `
        <div class="red-flag-item ${flag.severity}">
          <div class="red-flag-top">
            <span class="red-flag-severity ${flag.severity}">${flag.severity?.toUpperCase()}</span>
            <span class="red-flag-category">${flag.category}</span>
          </div>
          <div class="red-flag-quote">"${flag.quote}"</div>
          <div class="red-flag-note">${flag.note}</div>
        </div>
      `).join('')}
    </div>
  `;
}

// ── Client delivery ────────────────────────────────────────────────────────────
function navigateToDelivery() {
  const session = AppState.session;
  const props = session?.properties || [];

  // Update delivery summary counts
  const confirmed = props.filter(p => p.status === 'confirmed').length;
  const declined = props.filter(p => p.status === 'declined').length;
  const pending = props.filter(p => !['confirmed','declined'].includes(p.status)).length;

  const el = id => document.getElementById(id);
  if (el('delivery-count-confirmed')) el('delivery-count-confirmed').textContent = confirmed;
  if (el('delivery-count-declined')) el('delivery-count-declined').textContent = declined;
  if (el('delivery-count-pending')) el('delivery-count-pending').textContent = pending;

  // Pre-fill client email
  const emailInput = $('delivery-email');
  if (emailInput && session?.client?.email) {
    emailInput.value = session.client.email;
  }

  showScreen('delivery');
}

async function handleBuildClientPage() {
  const showRedFlags = $('toggle-red-flags')?.checked || false;

  showPlan([
    'Generating client-facing showing day HTML page',
    'Calling client_page_builder.py via /api/build-client-page',
    'Creating /output/client_[date]_[name]/index.html with property cards',
    'On failure: display error with manual option'
  ]);

  const btn = $('btn-build-page');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Building...'; }

  try {
    const result = await apiFetch('/api/build-client-page', {
      method: 'POST',
      body: { show_red_flags: showRedFlags }
    });

    hidePlan();

    if (result.status === 'success') {
      const path = result.data?.relative_path || '';
      const previewUrl = `/${path}`;
      $('client-page-preview-link').href = previewUrl;
      $('client-page-preview-link').style.display = 'inline-flex';
      showToast('Client page built', 'Ready to preview and send.', 'success');
    } else {
      showToast('Build failed', result.error || 'Unknown error', 'error');
    }
  } catch (e) {
    hidePlan();
    showToast('Error', e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = 'Build Client Page'; }
  }
}

async function handleSendToClient() {
  const email = $('delivery-email')?.value?.trim();
  if (!email) {
    showToast('Email required', 'Enter the client email address.', 'warning');
    return;
  }

  const confirmed = confirm(`Send showing day page to ${email}?`);
  if (!confirmed) return;

  const session = AppState.session;
  const pageUrl = session?.client_page_path
    ? `http://localhost:5000/${session.client_page_path.split('/').slice(-3).join('/')}`
    : '';

  showPlan([
    `Sending showing day page to ${email}`,
    'Calling gmail_sender.py via /api/send-client-email',
    'Email includes page link + calendar invite option',
    'On failure: display copyable email draft'
  ]);

  const btn = $('btn-send-client');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Sending...'; }

  try {
    const result = await apiFetch('/api/send-client-email', {
      method: 'POST',
      body: {
        to_email: email,
        client_name: session?.client?.name || '',
        page_url: pageUrl,
        session_date: session?.session_date || ''
      }
    });

    hidePlan();

    if (result.status === 'success') {
      showToast('Email sent!', `Delivered to ${email}`, 'success');
      $('email-draft-modal')?.classList.remove('visible');
    } else {
      // Show email draft as fallback
      const draft = result.data?.plain_text || '';
      const draftBody = $('email-draft-body');
      if (draftBody && draft) draftBody.textContent = draft;
      $('email-draft-modal')?.classList.add('visible');
      showToast('Gmail not configured', 'Use the draft below to send manually.', 'warning', 7000);
    }
  } catch (e) {
    hidePlan();
    showToast('Error', e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = 'Send to Client'; }
  }
}

// ── Plan display ───────────────────────────────────────────────────────────────
function showPlan(steps) {
  const el = $('plan-display');
  const list = $('plan-steps');
  if (!el || !list) return;
  list.innerHTML = steps.map(s => `<li>${s}</li>`).join('');
  el.classList.add('visible');
}

function hidePlan() {
  $('plan-display')?.classList.remove('visible');
}

// ── Webhook polling ────────────────────────────────────────────────────────────
async function pollSession() {
  try {
    const data = await apiFetch('/api/session');
    if (data.status !== 'success') return;

    const newSession = data.data;
    const newHash = sessionHash(newSession);

    if (AppState.lastPollHash && newHash !== AppState.lastPollHash) {
      // Something changed — find what
      const oldProps = AppState.session?.properties || [];
      const newProps = newSession.properties || [];

      newProps.forEach(newProp => {
        const oldProp = oldProps.find(p => p.address === newProp.address);
        if (oldProp && oldProp.status !== newProp.status) {
          const msg = `${newProp.address.split(',')[0]} — ${statusLabel(newProp.status)}`;
          showWebhookNotification(msg);
          showToast('Status updated', msg, newProp.status === 'confirmed' ? 'success' : 'info');
        }
      });

      AppState.session = newSession;
      updateStatusBar();
      if (AppState.currentScreen === 'status') {
        renderPropertyStatusCards();
      }
    }

    AppState.lastPollHash = newHash;
    AppState.session = newSession;
  } catch (e) {
    // Silent fail on polling
  }
}

// ── Clipboard helpers ──────────────────────────────────────────────────────────
function copyToClipboard(elementId) {
  const el = $(elementId);
  if (!el) return;
  const text = el.innerText || el.textContent;
  navigator.clipboard.writeText(text).then(() => {
    showToast('Copied', 'Checklist copied to clipboard.', 'success', 2000);
  }).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('Copied', 'Checklist copied.', 'success', 2000);
  });
}

// ── Reset session ──────────────────────────────────────────────────────────────
async function handleResetSession() {
  const confirmed = confirm('Reset session? All current data will be cleared. This cannot be undone.');
  if (!confirmed) return;

  try {
    await apiFetch('/api/session/reset', { method: 'POST' });
    AppState.session = null;
    AppState.client = null;
    AppState.addresses = [''];
    AppState.route = null;
    clearMapMarkers();
    updateStatusBar();
    renderAddressList();
    $('client-confirm-card')?.classList.remove('visible');
    $('client-manual-entry')?.classList.remove('visible');
    $('client-lookup-input').value = '';
    showScreen('start');
    showToast('Session reset', 'Starting fresh.', 'info');
  } catch (e) {
    showToast('Reset failed', e.message, 'error');
  }
}

// ── Settings ───────────────────────────────────────────────────────────────────
const SETTINGS_KEY = 'showingday_settings';

const SETTINGS_FIELDS = [
  'agent-name', 'brokerage', 'home-address', 'office-address',
  'default-showing-min', 'default-direction',
  'lofty-api-key', 'ghl-api-key', 'ghl-location-id',
  'showingtime-api-key', 'sentrikey-api-key', 'fub-api-key', 'gmaps-api-key'
];

// Notification toggle IDs — each maps to a checkbox
const NOTIF_TOGGLE_IDS = [
  'notif-requested-agent-sms',  'notif-requested-agent-email',
  'notif-requested-client-sms', 'notif-requested-client-email',
  'notif-confirmed-agent-sms',  'notif-confirmed-agent-email',
  'notif-confirmed-client-sms', 'notif-confirmed-client-email',
  'notif-rescheduled-agent-sms',  'notif-rescheduled-agent-email',
  'notif-rescheduled-client-sms', 'notif-rescheduled-client-email',
  'notif-canceled-agent-sms',  'notif-canceled-agent-email',
  'notif-canceled-client-sms', 'notif-canceled-client-email',
];

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
    SETTINGS_FIELDS.forEach(key => {
      const el = $(`setting-${key}`);
      if (el && saved[key] !== undefined) el.value = saved[key];
    });

    // Load notification toggles (checkboxes)
    NOTIF_TOGGLE_IDS.forEach(id => {
      const el = $(id);
      if (el && saved[id] !== undefined) el.checked = saved[id] === true || saved[id] === 'true';
    });

    updateIntegrationBadges(saved);

    // Pre-fill start address from home address if empty
    const startEl = $('start-address');
    if (startEl && !startEl.value && saved['home-address']) {
      startEl.value = saved['home-address'];
    }
  } catch (e) {
    console.warn('Could not load settings:', e);
  }
}

function saveSettings() {
  const saved = {};
  SETTINGS_FIELDS.forEach(key => {
    const el = $(`setting-${key}`);
    if (el) saved[key] = el.value;
  });

  // Save notification toggles
  NOTIF_TOGGLE_IDS.forEach(id => {
    const el = $(id);
    if (el) saved[id] = el.checked;
  });

  localStorage.setItem(SETTINGS_KEY, JSON.stringify(saved));
  updateIntegrationBadges(saved);

  // Sync home/office into AppState.config for use in route planning
  if (saved['home-address']) AppState.config.default_start_address = saved['home-address'];
  if (saved['office-address']) AppState.config.office_address = saved['office-address'];

  const msg = $('settings-saved-msg');
  if (msg) { msg.style.display = 'block'; setTimeout(() => msg.style.display = 'none', 3000); }
}

// Helper: get current notification preferences from localStorage
function getNotificationPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
    const prefs = {};
    NOTIF_TOGGLE_IDS.forEach(id => { prefs[id] = saved[id] === true || saved[id] === 'true'; });
    return prefs;
  } catch (e) {
    return {};
  }
}

function updateIntegrationBadges(settings) {
  const badges = {
    'badge-lofty':       settings['lofty-api-key'],
    'badge-ghl':         settings['ghl-api-key'],
    'badge-showingtime': settings['showingtime-api-key'],
    'badge-sentrikey':   settings['sentrikey-api-key'],
    'badge-fub':         settings['fub-api-key'],
    'badge-gmaps':       settings['gmaps-api-key'] || AppState.config?.maps_key,
  };
  Object.entries(badges).forEach(([id, val]) => {
    const el = $(id);
    if (!el) return;
    if (val) {
      el.textContent = 'Configured';
      el.className = 'integration-badge badge-active';
    } else {
      el.textContent = 'Not configured';
      el.className = 'integration-badge badge-inactive';
    }
  });
}

// ── Debounce utility ───────────────────────────────────────────────────────────
function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ── Clients screen ─────────────────────────────────────────────────────────────

/** Avatar colors — pick by simple name hash mod 5 */
const AVATAR_COLORS = ['#C9A84C', '#4a9eff', '#4caf88', '#9b59b6', '#e67e22'];

function _avatarColor(name) {
  if (!name) return AVATAR_COLORS[0];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff;
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}

function _initials(name) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Format a date string as a human-friendly relative label.
 * "Today", "Tomorrow", "Yesterday", "Mar 15", or "Mar 15, 2025"
 */
function formatRelativeDate(dateStr) {
  if (!dateStr) return '—';
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  if (dateStr === todayStr) return 'Today';

  const target = new Date(dateStr + 'T12:00:00');
  const diff = Math.round((target - today) / 86400000);

  if (diff === 1) return 'Tomorrow';
  if (diff === -1) return 'Yesterday';

  const thisYear = today.getFullYear() === target.getFullYear();
  return target.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(thisYear ? {} : { year: 'numeric' })
  });
}

/**
 * Load the Clients screen: fetch data, update stats, render list.
 */
async function loadClientsScreen() {
  const listEl = $('clients-list');
  if (!listEl) return;

  // Show loading state
  listEl.innerHTML = '<div class="clients-loading"><span class="spinner">⏳</span> Loading clients…</div>';

  try {
    const result = await apiFetch('/api/clients');
    if (result.status === 'success') {
      const clients = result.data.clients || [];
      _updateClientsStats(clients);
      renderClientsList(clients);
      // Store for search filtering
      window._allClients = clients;
    } else {
      listEl.innerHTML = '<div class="clients-empty"><div class="empty-icon">⚠️</div><h3>Could not load clients</h3><p>Try refreshing the page.</p></div>';
    }
  } catch (e) {
    listEl.innerHTML = '<div class="clients-empty"><div class="empty-icon">⚠️</div><h3>Could not load clients</h3><p>' + (e.message || 'Network error') + '</p></div>';
  }
}

function _updateClientsStats(clients) {
  const today = new Date();
  const thisMonthStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`;
  const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  let totalSessions = 0;
  let upcoming = 0;
  let thisMonth = 0;

  clients.forEach(c => {
    const sessions = c.sessions || [];
    totalSessions += sessions.length;
    sessions.forEach(s => {
      if (s.date && s.date >= todayStr) upcoming++;
      if (s.date && s.date.startsWith(thisMonthStr)) thisMonth++;
    });
  });

  const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
  set('stat-total-clients',   clients.length);
  set('stat-total-showings',  totalSessions);
  set('stat-upcoming-showings', upcoming);
  set('stat-this-month',      thisMonth);
}

/**
 * Render all client cards into #clients-list.
 */
function renderClientsList(clients) {
  const listEl = $('clients-list');
  if (!listEl) return;

  if (!clients || clients.length === 0) {
    listEl.innerHTML = `
      <div class="clients-empty">
        <div class="empty-icon">👥</div>
        <h3>No clients yet</h3>
        <p>Add your first client or run a showing session to get started.</p>
      </div>
    `;
    return;
  }

  listEl.innerHTML = '';
  clients.forEach(client => {
    const card = _buildClientCard(client);
    listEl.appendChild(card);
  });
}

function _buildClientCard(client) {
  const wrapper = document.createElement('div');
  wrapper.className = 'client-card';
  wrapper.dataset.clientId = client.id;

  const color = _avatarColor(client.name);
  const initials = _initials(client.name);
  const past = client.past_sessions || 0;
  const future = client.future_sessions || 0;
  const lastDate = client.last_showing_date ? formatRelativeDate(client.last_showing_date) : '—';
  const nextDate = client.next_showing_date ? formatRelativeDate(client.next_showing_date) : '—';

  const contactParts = [];
  if (client.email) contactParts.push(client.email);
  if (client.phone) contactParts.push(client.phone);
  const contactStr = contactParts.join(' · ') || 'No contact info';

  wrapper.innerHTML = `
    <div class="client-card-row" data-expand="${client.id}">
      <div class="client-avatar" style="background:${color};">${initials}</div>
      <div class="client-info">
        <div class="client-name">${_escHtml(client.name)}</div>
        <div class="client-contact">${_escHtml(contactStr)}</div>
      </div>
      <div class="client-stats-inline">
        <div class="client-stat-inline">
          <div class="num">${past}</div>
          <div class="lbl">Past</div>
        </div>
        <div class="client-stat-inline">
          <div class="num">${future}</div>
          <div class="lbl">Upcoming</div>
        </div>
        <div class="client-stat-inline">
          <div class="num" style="font-size:12px;font-weight:500;">${lastDate}</div>
          <div class="lbl">Last</div>
        </div>
      </div>
      <div class="client-actions" onclick="event.stopPropagation()">
        <button class="btn btn-sm btn-primary" onclick="startSessionForClient(${JSON.stringify(client).replace(/"/g,'&quot;')})">▶ Start Session</button>
        <div class="client-menu-wrap">
          <button class="client-menu-btn" onclick="toggleClientMenu('${client.id}', event)">⋯</button>
          <div class="client-menu-popup" id="menu-${client.id}" style="display:none;">
            <button onclick="showClientHistory('${client.id}'); closeAllClientMenus();">View History</button>
            <button onclick="handleEditClient('${client.id}'); closeAllClientMenus();">Edit</button>
            <button class="danger" onclick="handleRemoveClient('${client.id}'); closeAllClientMenus();">Remove</button>
          </div>
        </div>
      </div>
    </div>
    <div class="client-history-panel" id="history-${client.id}" style="display:none;">
      ${renderClientHistory(client)}
    </div>
  `;

  // Expand/collapse on row click
  const row = wrapper.querySelector('.client-card-row');
  row.addEventListener('click', () => toggleClientHistory(client.id));

  return wrapper;
}

function _escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/**
 * Returns the HTML string for the inline history panel.
 */
function renderClientHistory(client) {
  const sessions = (client.sessions || []).slice().sort((a, b) => {
    if (!a.date) return 1;
    if (!b.date) return -1;
    return b.date.localeCompare(a.date);
  });

  if (sessions.length === 0) {
    return '<p style="font-size:13px;color:var(--text-muted);">No sessions recorded yet.</p>';
  }

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  const rows = sessions.map(s => {
    let dotClass = 'session-dot';
    let badgeClass = 'session-status-badge completed';
    let badgeLabel = 'Completed';

    if (s.status === 'in-progress' || s.status === 'in_progress') {
      dotClass = 'session-dot in-progress';
      badgeClass = 'session-status-badge in-progress';
      badgeLabel = 'In Progress';
    } else if (s.date && s.date >= todayStr && s.status !== 'completed') {
      dotClass = 'session-dot upcoming';
      badgeClass = 'session-status-badge upcoming';
      badgeLabel = 'Upcoming';
    }

    const propList = (s.properties || []).join(', ') || 'No properties recorded';
    const propCount = s.properties_shown || (s.properties || []).length || 0;

    return `
      <div class="session-row">
        <div class="${dotClass}"></div>
        <div class="session-info">
          <div class="session-date">
            ${_escHtml(formatRelativeDate(s.date))}
            <span class="${badgeClass}">${badgeLabel}</span>
          </div>
          <div class="session-props">${propCount} propert${propCount === 1 ? 'y' : 'ies'} · ${_escHtml(propList)}</div>
        </div>
      </div>
    `;
  }).join('');

  return `<div class="session-timeline">${rows}</div>`;
}

function toggleClientHistory(clientId) {
  const panel = $(`history-${clientId}`);
  if (!panel) return;
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

function showClientHistory(clientId) {
  const panel = $(`history-${clientId}`);
  if (panel) panel.style.display = 'block';
}

function toggleClientMenu(clientId, event) {
  event.stopPropagation();
  const menu = $(`menu-${clientId}`);
  if (!menu) return;
  const isVisible = menu.style.display !== 'none';
  closeAllClientMenus();
  if (!isVisible) menu.style.display = 'block';
}

function closeAllClientMenus() {
  document.querySelectorAll('.client-menu-popup').forEach(m => { m.style.display = 'none'; });
}

// Close menus on outside click
document.addEventListener('click', () => closeAllClientMenus());

/**
 * Filter rendered client cards by name substring.
 * Also queries the CRM lookup endpoint for "Import from CRM" suggestions.
 */
async function clientSearchFilter(query) {
  const allClients = window._allClients || [];
  const q = query.trim().toLowerCase();

  // Filter rendered cards
  document.querySelectorAll('.client-card').forEach(card => {
    const nameEl = card.querySelector('.client-name');
    const name = (nameEl?.textContent || '').toLowerCase();
    card.style.display = (!q || name.includes(q)) ? '' : 'none';
  });

  const dropdown = $('client-search-dropdown');
  if (!dropdown) return;

  if (!q || q.length < 2) {
    dropdown.style.display = 'none';
    return;
  }

  // Check if there are CRM matches to suggest
  try {
    const result = await apiFetch('/api/client-lookup', {
      method: 'POST',
      body: { name: query }
    });

    if (result.status === 'success' && result.data && !result.data.not_found) {
      const crm = result.data;
      // Only show if not already in local list
      const alreadyExists = allClients.some(c => c.name?.toLowerCase() === crm.name?.toLowerCase());
      if (!alreadyExists) {
        dropdown.style.display = 'block';
        dropdown.innerHTML = `
          <div class="client-search-result" onclick="handleAddClient(${JSON.stringify(crm).replace(/"/g,'&quot;')})">
            <div>
              <div style="font-weight:600;">${_escHtml(crm.name)}</div>
              <div class="client-search-result-label">Import from ${(crm.crm_source||'CRM').toUpperCase()} · ${_escHtml(crm.email||'')} ${_escHtml(crm.phone||'')}</div>
            </div>
          </div>
        `;
        return;
      }
    }
  } catch (e) {
    // CRM unreachable — suppress dropdown
  }

  dropdown.style.display = 'none';
}

/**
 * Open the Add Client modal.
 * Optionally pre-fill with a client object (from CRM suggestion).
 */
function handleAddClient(prefill) {
  // Remove any existing modal
  const existing = document.getElementById('add-client-modal');
  if (existing) existing.remove();

  const defaults = prefill || {};

  const overlay = document.createElement('div');
  overlay.className = 'add-client-modal-overlay';
  overlay.id = 'add-client-modal';

  overlay.innerHTML = `
    <div class="add-client-modal-box">
      <h3>Add Client</h3>

      <div class="form-field">
        <label>Full Name *</label>
        <input type="text" id="acm-name" placeholder="First and Last Name" value="${_escHtml(defaults.name||'')}">
      </div>
      <div class="form-field">
        <label>Email</label>
        <input type="email" id="acm-email" placeholder="client@email.com" value="${_escHtml(defaults.email||'')}">
      </div>
      <div class="form-field">
        <label>Phone</label>
        <input type="text" id="acm-phone" placeholder="(616) 555-0000" value="${_escHtml(defaults.phone||'')}">
      </div>
      <div class="form-field">
        <label>CRM Source</label>
        <select id="acm-crm-source">
          <option value="manual" ${defaults.crm_source==='manual'||!defaults.crm_source?'selected':''}>Manual</option>
          <option value="lofty" ${defaults.crm_source==='lofty'?'selected':''}>Lofty</option>
          <option value="ghl" ${defaults.crm_source==='ghl'?'selected':''}>GHL / Lead Connector</option>
        </select>
      </div>

      <div class="add-client-modal-actions">
        <button class="btn btn-secondary" onclick="document.getElementById('add-client-modal').remove()">Cancel</button>
        <button class="btn btn-primary" id="acm-save-btn" onclick="saveNewClient()">Save Client</button>
      </div>
    </div>
  `;

  // Close on backdrop click
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.remove();
  });

  document.body.appendChild(overlay);

  // Focus the name field (or email if name is pre-filled)
  setTimeout(() => {
    const nameInput = document.getElementById('acm-name');
    if (nameInput) {
      if (defaults.name) {
        document.getElementById('acm-email')?.focus();
      } else {
        nameInput.focus();
      }
    }
  }, 50);
}

async function saveNewClient() {
  const name  = (document.getElementById('acm-name')?.value || '').trim();
  const email = (document.getElementById('acm-email')?.value || '').trim();
  const phone = (document.getElementById('acm-phone')?.value || '').trim();
  const crmSource = document.getElementById('acm-crm-source')?.value || 'manual';

  if (!name) {
    showToast('Name required', 'Please enter the client name.', 'warning');
    return;
  }

  const btn = document.getElementById('acm-save-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

  try {
    const result = await apiFetch('/api/clients', {
      method: 'POST',
      body: { name, email, phone, crm_source: crmSource }
    });

    if (result.status === 'success') {
      document.getElementById('add-client-modal')?.remove();
      showToast('Client saved', `${name} added to your client list.`, 'success');
      $('client-search-input').value = '';
      await loadClientsScreen();
    } else {
      showToast('Save failed', result.error || 'Could not save client.', 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Save Client'; }
    }
  } catch (e) {
    showToast('Save failed', e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Save Client'; }
  }
}

/**
 * Pre-fill the Add Client modal with existing data for editing.
 */
async function handleEditClient(clientId) {
  const allClients = window._allClients || [];
  const client = allClients.find(c => c.id === clientId);
  if (!client) {
    showToast('Client not found', '', 'error');
    return;
  }
  handleAddClient(client);
}

/**
 * Remove a client after confirmation.
 */
async function handleRemoveClient(clientId) {
  const allClients = window._allClients || [];
  const client = allClients.find(c => c.id === clientId);
  const name = client?.name || clientId;

  // Use the existing confirm modal
  const modal = $('confirm-modal');
  const title = $('modal-title');
  const msg = $('modal-message');
  const confirmBtn = $('btn-confirm-modal');

  if (modal && title && msg && confirmBtn) {
    title.textContent = 'Remove Client';
    msg.textContent = `Remove ${name} from your client list? This cannot be undone.`;
    modal.classList.add('visible');

    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    newBtn.addEventListener('click', async () => {
      modal.classList.remove('visible');
      try {
        const result = await apiFetch(`/api/clients/${encodeURIComponent(clientId)}`, { method: 'DELETE' });
        if (result.status === 'success') {
          showToast('Client removed', `${name} has been removed.`, 'success');
          await loadClientsScreen();
        } else {
          showToast('Remove failed', result.error || '', 'error');
        }
      } catch (e) {
        showToast('Remove failed', e.message, 'error');
      }
    }, { once: true });
  } else {
    // Fallback: just delete
    if (!confirm(`Remove ${name}?`)) return;
    const result = await apiFetch(`/api/clients/${encodeURIComponent(clientId)}`, { method: 'DELETE' });
    if (result.status === 'success') {
      showToast('Client removed', '', 'success');
      await loadClientsScreen();
    }
  }
}

/**
 * Pre-fill AppState.client with the selected client and switch to Session Setup.
 */
function startSessionForClient(client) {
  AppState.client = {
    name: client.name,
    email: client.email,
    phone: client.phone,
    crm_source: client.crm_source || 'manual'
  };

  // Show the client confirmation card on Session Setup screen
  showClientCard(AppState.client);

  // Persist to session
  apiFetch('/api/session/update', { method: 'POST', body: { client: AppState.client } });

  // Switch to session setup tab
  showScreen('start');
  showToast('Client loaded', `${client.name} pre-filled for the new session.`, 'success');
}

// ── Event binding ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Initialize with one blank address row
  AppState.addresses = [''];
  renderAddressList();
  initReturnDestinationToggle();
  initModeSelector();
  loadSettings();

  // Settings save button
  $('btn-save-settings')?.addEventListener('click', saveSettings);

  // Autocomplete on settings address fields
  ['setting-home-address', 'setting-office-address'].forEach(id => {
    const el = $(id);
    if (el) attachAutocompleteWhenReady(el);
  });

  // Load config and session
  Promise.all([loadConfig(), loadSession()]);

  // Attach autocomplete to start-address field once Maps loads
  const startAddrInput = $('start-address');
  if (startAddrInput) attachAutocompleteWhenReady(startAddrInput);

  // Start polling every 10 seconds
  AppState.pollInterval = setInterval(pollSession, 10000);

  // --- Nav tabs ---
  $$('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => showScreen(tab.dataset.screen));
  });

  // --- Client lookup ---
  const lookupInput = $('client-lookup-input');
  const lookupBtn = $('btn-lookup');

  if (lookupInput) {
    lookupInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') handleClientLookup(lookupInput.value);
    });
  }

  if (lookupBtn) {
    lookupBtn.addEventListener('click', () => handleClientLookup(lookupInput?.value || ''));
  }

  // --- Manual client entry ---
  $('btn-manual-entry')?.addEventListener('click', () => showManualEntry());
  $('btn-save-manual-client')?.addEventListener('click', saveManualClient);

  // --- Add address (single-client mode) ---
  $('btn-add-address')?.addEventListener('click', () => addAddressRow());

  // --- Add client group (multi-client mode) ---
  $('btn-add-client-group')?.addEventListener('click', () => addClientGroup());

  // --- Optimize route ---
  $('btn-optimize')?.addEventListener('click', handleOptimizeRoute);

  // --- Route screen ---
  $('btn-add-calendar')?.addEventListener('click', handleAddToCalendar);
  $('btn-edit-route')?.addEventListener('click', () => showScreen('start'));
  $('btn-goto-status')?.addEventListener('click', () => {
    renderPropertyStatusCards();
    showScreen('status');
  });

  // --- Status screen ---
  $('btn-goto-delivery')?.addEventListener('click', navigateToDelivery);

  // --- Delivery screen ---
  $('btn-build-page')?.addEventListener('click', handleBuildClientPage);
  $('btn-send-client')?.addEventListener('click', handleSendToClient);

  // --- Reset ---
  $('btn-reset-session')?.addEventListener('click', handleResetSession);

  // --- Webhook strip dismiss ---
  document.querySelector('.webhook-dismiss')?.addEventListener('click', () => {
    $('webhook-strip')?.classList.remove('visible');
  });

  // --- Modal close ---
  $('btn-close-modal')?.addEventListener('click', () => {
    $('confirm-modal')?.classList.remove('visible');
  });

  // --- Email draft modal ---
  $('btn-close-email-draft')?.addEventListener('click', () => {
    $('email-draft-modal')?.classList.remove('visible');
  });

  $('btn-copy-email-draft')?.addEventListener('click', () => {
    copyToClipboard('email-draft-body');
  });

  // --- Direction toggle ---
  $$('.direction-toggle button').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.direction-toggle button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // Set default date to today
  const dateInput = $('session-date');
  if (dateInput && !dateInput.value) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    dateInput.value = `${yyyy}-${mm}-${dd}`;
  }

  // Set default times
  const startTimeInput = $('start-time');
  if (startTimeInput && !startTimeInput.value) startTimeInput.value = '13:00';
  const endTimeInput = $('end-time');
  if (endTimeInput && !endTimeInput.value) endTimeInput.value = '18:00';

  // --- Clients screen ---
  $('client-search-input')?.addEventListener('input', debounce(e => clientSearchFilter(e.target.value), 300));
  $('btn-add-client')?.addEventListener('click', () => handleAddClient());

  // Hide client search dropdown on outside click
  document.addEventListener('click', e => {
    const wrap = document.querySelector('.clients-search-wrap');
    const dropdown = $('client-search-dropdown');
    if (dropdown && wrap && !wrap.contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });

  // Load clients screen when its tab is clicked
  $$('.nav-tab').forEach(tab => {
    if (tab.dataset.screen === 'clients') {
      tab.addEventListener('click', loadClientsScreen);
    }
  });
});
