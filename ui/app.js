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

// ── Route rendering ────────────────────────────────────────────────────────────
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

  // Sidebar stops
  sidebar.innerHTML = route.map(stop => {
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
  script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&callback=initGoogleMapsAutocomplete`;
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

  const geocoder = new google.maps.Geocoder();
  const bounds = new google.maps.LatLngBounds();
  const routeCoords = [];

  // Geocode each address and place numbered markers
  const geocodePromises = route.map((stop, idx) => {
    return new Promise(resolve => {
      geocoder.geocode({ address: stop.address }, (results, status) => {
        if (status === 'OK') {
          const pos = results[0].geometry.location;
          bounds.extend(pos);
          routeCoords[idx] = pos;

          // Custom numbered marker
          const marker = new google.maps.Marker({
            position: pos,
            map: AppState.map,
            label: {
              text: String(stop.order),
              color: '#0D1B2A',
              fontWeight: 'bold',
              fontSize: '12px'
            },
            icon: {
              path: google.maps.SymbolPath.CIRCLE,
              scale: 16,
              fillColor: '#C9A84C',
              fillOpacity: 1,
              strokeColor: '#0D1B2A',
              strokeWeight: 2
            },
            title: `${stop.order}. ${stop.address}\n${stop.showing_start} – ${stop.showing_end}`
          });

          AppState.mapMarkers.push(marker);
          resolve();
        } else {
          routeCoords[idx] = null;
          resolve();
        }
      });
    });
  });

  Promise.all(geocodePromises).then(() => {
    // Draw polyline connecting stops in order
    const validCoords = routeCoords.filter(Boolean);
    if (validCoords.length > 1) {
      AppState.mapPolyline = new google.maps.Polyline({
        path: validCoords,
        geodesic: true,
        strokeColor: '#C9A84C',
        strokeOpacity: 0.6,
        strokeWeight: 2
      });
      AppState.mapPolyline.setMap(AppState.map);
    }
    if (validCoords.length > 0) {
      AppState.map.fitBounds(bounds, { padding: 60 });
    }
  });
}

// ── Calendar ───────────────────────────────────────────────────────────────────
async function handleAddToCalendar() {
  const session = AppState.session || {};
  const route = AppState.route || session.route || [];

  if (route.length === 0) {
    showToast('No route', 'Optimize a route first.', 'warning');
    return;
  }

  showPlan([
    `Creating Google Calendar events for ${route.length} showings`,
    'Calling calendar_manager.py via /api/calendar/create',
    'Creating TENTATIVE showing blocks + travel blocks for each stop',
    'On failure: export .ics file for manual calendar import'
  ]);

  const btn = $('btn-add-calendar');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Adding...'; }

  try {
    const result = await apiFetch('/api/calendar/create', {
      method: 'POST',
      body: {
        route,
        client_name: session.client?.name || AppState.client?.name || '',
        session_date: session.session_date || ''
      }
    });

    hidePlan();

    if (result.status === 'success') {
      showToast('Calendar events created', 'Tentative blocks added to your calendar.', 'success');
      // Update session
      AppState.session = (await apiFetch('/api/session')).data;
      updateStatusBar();
      showScreen('status');
      renderPropertyStatusCards();
    } else if (result.status === 'fallback') {
      // ICS download fallback
      if (result.data?.ics_content) {
        downloadICS(result.data.ics_content, session.session_date);
        showToast('ICS file downloaded', 'Import this file into your calendar app manually.', 'warning', 7000);
      } else {
        showToast('Calendar unavailable', result.error || 'Configure Google Calendar to enable.', 'warning');
      }
      showScreen('status');
      renderPropertyStatusCards();
    } else {
      showToast('Calendar failed', result.error || 'Unknown error', 'error');
    }
  } catch (e) {
    hidePlan();
    showToast('Error', e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = 'Add to Calendar'; }
  }
}

function downloadICS(content, sessionDate) {
  const blob = new Blob([content], { type: 'text/calendar' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `showings_${sessionDate || 'today'}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
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

      // If declined, prompt calendar deletion
      const prop = AppState.session?.properties?.find(p => p.address === address);
      if (status === 'declined' && prop?.calendar_event_id) {
        if (confirm(`Delete calendar event for ${address.split(',')[0]}?`)) {
          await apiFetch('/api/calendar/delete', {
            method: 'POST',
            body: { event_id: prop.calendar_event_id, address }
          });
        }
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

// ── Event binding ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Initialize with one blank address row
  AppState.addresses = [''];
  renderAddressList();
  initReturnDestinationToggle();

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

  // --- Add address ---
  $('btn-add-address')?.addEventListener('click', () => addAddressRow());

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
});
