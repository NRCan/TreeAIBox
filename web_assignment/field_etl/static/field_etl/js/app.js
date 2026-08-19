/* field_etl app.js — Step 1 map + controls */
(function () {
  const srcPath = document.getElementById('srcPath');
  const layerSel = document.getElementById('layerSel');
  const scanBtn = document.getElementById('scanBtn');
  const pickBtn = document.getElementById('pickBtn');
  const loadBtn = document.getElementById('loadBtn');
  const deriveDbh = document.getElementById('deriveDbh');
  const bufferRange = document.getElementById('bufferRange');
  const bufferVal = document.getElementById('bufferVal');
  const showLabels = document.getElementById('showLabels');
  const labelField = document.getElementById('labelField');
  const stTotal = document.getElementById('stTotal');
  const stClean = document.getElementById('stClean');
  const stAnom = document.getElementById('stAnom');
  const stDerived = document.getElementById('stDerived');
  const stCrs = document.getElementById('stCrs');
  const summaryBar = document.getElementById('summaryBar');
  const infoText = document.getElementById('infoText');

  let state = { path: '', layer: '', deriveDbh: true, stats: null };

  // --- map ---
  const map = L.map('map', { maxZoom: 24, maxNativeZoom: 19 }).setView([44.98, -65.08], 15);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxNativeZoom: 19, maxZoom: 24,
    attribution: '&copy; OpenStreetMap contributors', referrerPolicy: 'origin'
  }).addTo(map);

  const layers = {
    points: L.layerGroup().addTo(map),
    flagged: L.layerGroup().addTo(map),
    line: L.layerGroup().addTo(map),
    boundary: L.layerGroup().addTo(map),
  };
  const markerRefs = []; // {marker, props, flagged}
  let labelsOn = false;
  let labelMode = 'tree_id';

  function labelText(p) {
    switch (labelMode) {
      case 'species': return p.species;
      case 'dbh': return p.dbh_cm != null ? p.dbh_cm : '-';
      case 'perimeter': return p.perimeter_cm != null ? p.perimeter_cm : '-';
      case 'side': return p.side;
      case 'y': return p.y_axis_m != null ? p.y_axis_m : '-';
      default: return p.tree_id;
    }
  }
  function applyLabels() {
    markerRefs.forEach(({ marker, props }) => {
      marker.unbindTooltip();
      if (labelsOn) marker.bindTooltip(String(labelText(props)), { permanent: true, direction: 'right', className: 'tree-label' });
    });
  }

  function renderGeoJSON(geojson) {
    Object.values(layers).forEach(l => l.clearLayers());
    markerRefs.length = 0;
    geojson.features.forEach(f => {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      if (f.geometry.type === 'Point') {
        const flagged = p.flagged === true || (p.anomalies && p.anomalies !== '-');
        const color = flagged ? '#ef4444' : (p.side === 'Left' ? '#1e8449' : '#1a5276');
        const m = L.circleMarker([lat, lon], { radius: flagged ? 5 : 6, fillColor: color, fillOpacity: 0.9, color: '#fff', weight: 1 });
        m.bindPopup(
          '<strong>Tree ' + p.tree_id + '</strong> (' + (p.species||'-') + ')<br>' +
          'DBH: ' + (p.dbh_cm!=null?p.dbh_cm:'-') + ' cm<br>' +
          'Perimeter: ' + (p.perimeter_cm!=null?p.perimeter_cm:'-') + ' cm' + (p.dbh_derived ? ' (derived)' : '') + '<br>' +
          'Side: ' + p.side + '<br>Y: ' + p.y_axis_m + '<br>' +
          (flagged ? '<b style="color:#ef4444">' + p.anomalies + '</b>' : '')
        );
        m.addTo(flagged ? layers.flagged : layers.points);
        markerRefs.push({ marker: m, props: p });
      } else if (f.geometry.type === 'LineString') {
        L.polyline(f.geometry.coordinates.map(c => [c[1], c[0]]), { color: '#c0392b', weight: 4, dashArray: '8 6' }).addTo(layers.line);
      } else if (f.geometry.type === 'Polygon') {
        L.polygon(f.geometry.coordinates[0].map(c => [c[1], c[0]]), { color: '#a855f7', weight: 2, fillColor: '#a855f7', fillOpacity: 0.10, dashArray: '4 4' }).addTo(layers.boundary);
      }
    });
    applyLabels();
    try {
      const b = L.latLngBounds([]);
      Object.values(layers).forEach(l => l.eachLayer(x => b.extend(x.getBounds ? x.getBounds() : x.getLatLng())));
      map.fitBounds(b.pad(0.1));
    } catch (e) {}
  }

  // --- process ---
  function currentBuffer() { return parseFloat(bufferRange.value); }
  function loadData() {
    const path = srcPath.value.trim();
    if (!path) { infoText.textContent = 'Enter a source path first.'; return; }
    state.path = path; state.layer = layerSel.value; state.deriveDbh = deriveDbh.checked;
    infoText.textContent = 'Processing…';
    fetch('/field-etl/api/process/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, layer: state.layer, derive_dbh: state.deriveDbh, buffer_m: currentBuffer() })
    }).then(r => r.json()).then(d => {
      if (d.status !== 'ok') { infoText.textContent = 'Error: ' + d.message; return; }
      renderGeoJSON(d.geojson);
      state.stats = d.stats;
      stTotal.textContent = d.stats.total;
      stClean.textContent = d.stats.clean;
      stAnom.textContent = d.stats.anomalies;
      stDerived.textContent = d.stats.dbh_from_perimeter;
      stCrs.textContent = d.source_crs || '';
      summaryBar.classList.remove('hidden');
      infoText.textContent = 'Loaded ' + d.stats.clean + ' clean / ' + d.stats.total + ' total from ' + (d.layer || 'auto layer');
      renderAnomalies(d.anomalies);
    }).catch(e => { infoText.textContent = 'Error: ' + e; });
  }

  function renderAnomalies(items) {
    const panel = document.querySelector('.panel');
    const prev = document.getElementById('anomTable');
    if (prev) prev.remove();
    const wrap = document.createElement('div'); wrap.id = 'anomTable'; wrap.className = 'table-wrap';
    let h = '<table><thead><tr><th>Tree</th><th>DBH</th><th>Issues</th></tr></thead><tbody>';
    items.forEach(it => { h += '<tr class="flag-row"><td>' + it.tree_id + '</td><td>' + (it.dbh_cm!=null?it.dbh_cm:'-') + '</td><td>' + it.anomalies.join('; ') + '</td></tr>'; });
    h += '</tbody></table>';
    wrap.innerHTML = h;
    panel.appendChild(wrap);
    panel.scrollTop = panel.scrollHeight;
  }

  // --- boundary buffer recompute ---
  let bTimer = null, bSeq = 0;
  bufferRange.addEventListener('input', () => {
    bufferVal.textContent = bufferRange.value;
    if (!state.path) return;
    clearTimeout(bTimer);
    bTimer = setTimeout(() => {
      const seq = ++bSeq;
      fetch('/field-etl/api/boundary/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: state.path, layer: state.layer, derive_dbh: state.deriveDbh, buffer_m: currentBuffer() })
      }).then(r => r.json()).then(d => {
        if (seq !== bSeq || d.status !== 'ok') return;
        layers.boundary.clearLayers();
        if (d.polygon) {
          const coords = d.polygon.geometry.coordinates[0].map(c => [c[1], c[0]]);
          L.polygon(coords, { color: '#a855f7', weight: 2, fillColor: '#a855f7', fillOpacity: 0.10, dashArray: '4 4' }).addTo(layers.boundary);
        }
      }).catch(() => {});
    }, 150);
  });

  // --- layer manager toggles ---
  document.querySelectorAll('[data-layer]').forEach(cb => {
    cb.addEventListener('change', () => {
      const name = cb.dataset.layer;
      if (cb.checked) map.addLayer(layers[name]); else map.removeLayer(layers[name]);
    });
  });
  showLabels.addEventListener('change', () => { labelsOn = showLabels.checked; applyLabels(); });
  labelField.addEventListener('change', () => { labelMode = labelField.value; applyLabels(); });

  // --- scan layers ---
  function isCsvPath(p) { return /.(csv|txt)$/i.test(p.trim()); }
  scanBtn.addEventListener('click', () => {
    const path = srcPath.value.trim();
    if (!path) return;
    if (isCsvPath(path)) {
      layerSel.innerHTML = '';
      const o = document.createElement('option'); o.value = ''; o.textContent = 'CSV dataset (single)'; layerSel.appendChild(o);
      infoText.textContent = 'CSV source detected — ready to process.';
      return;
    }
    fetch('/field-etl/api/list-layers/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }) })
      .then(r => r.json()).then(d => {
        if (d.status !== 'ok') { infoText.textContent = 'Error: ' + d.message; return; }
        layerSel.innerHTML = '';
        d.layers.forEach(l => { const o = document.createElement('option'); o.value = l; o.textContent = l; layerSel.appendChild(o); });
        if (d.default_layer) layerSel.value = d.default_layer;
        infoText.textContent = d.layers.length + ' layer(s) found';
      }).catch(e => { infoText.textContent = 'Error: ' + e; });
  });

  // --- native picker ---
  pickBtn.addEventListener('click', () => {
    fetch('/field-etl/api/pick/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"type":"file"}' })
      .then(r => r.json()).then(d => { if (d.status === 'ok' && d.path) srcPath.value = d.path; }).catch(() => {});
  });

  loadBtn.addEventListener('click', loadData);

  // --- exports (use current buffer) ---
  function exportUrl(kind) {
    const params = new URLSearchParams({
      path: state.path || srcPath.value.trim(),
      layer: state.layer || '', buffer: currentBuffer(),
      exclude: '1', derive_dbh: state.deriveDbh ? '1' : '0'
    });
    return ('/field-etl/export/' + kind + '/?' + params.toString());
  }
  document.getElementById('exportGpkg').addEventListener('click', () => { window.open(exportUrl('gpkg'), '_blank'); });
  document.getElementById('exportGeoJson').addEventListener('click', () => { window.open(exportUrl('geojson'), '_blank'); });
  document.getElementById('exportCsv').addEventListener('click', () => { window.open(exportUrl('csv'), '_blank'); });
})();
