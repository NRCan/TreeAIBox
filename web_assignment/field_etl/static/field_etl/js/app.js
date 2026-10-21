/* field_etl app.js — Step 1 map + controls (Interactive Studio UI) */
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
  const badgeCleanCount = document.getElementById('badgeCleanCount');
  const badgeAnomCount = document.getElementById('badgeAnomCount');
  const anomListCount = document.getElementById('anomListCount');
  const anomCard = document.getElementById('anomalyInspectorCard');
  const anomTableWrap = document.getElementById('anomTableWrap');

  const inspectorCard = document.getElementById('treeInspectorCard');
  const inspectorBadge = document.getElementById('inspectorTreeBadge');
  const inspectorContent = document.getElementById('inspectorContent');

  const btnToggleLegend = document.getElementById('btnToggleLegend');
  const btnCloseLegend = document.getElementById('btnCloseLegend');
  const mapLegend = document.getElementById('mapLegend');
  const btnResetMapZoom = document.getElementById('btnResetMapZoom');

  let state = { path: '', layer: '', deriveDbh: true, stats: null };
  let selectedMarkerRef = null;

  // --- GIS Map Setup ---
  const map = L.map('map', { maxZoom: 24, maxNativeZoom: 19, zoomControl: true }).setView([44.98, -65.08], 15);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxNativeZoom: 19, maxZoom: 24,
    attribution: '&copy; OpenStreetMap contributors', referrerPolicy: 'origin'
  }).addTo(map);

  const layers = {
    points: L.layerGroup().addTo(map),
    flagged: L.layerGroup().addTo(map),
    line: L.layerGroup().addTo(map),
    boundary: L.layerGroup().addTo(map),
    selection: L.layerGroup().addTo(map),
  };
  const markerRefs = []; // {marker, props, flagged, lat, lon}
  let labelsOn = false;
  let labelMode = 'tree_id';

  function labelText(p) {
    switch (labelMode) {
      case 'species': return p.species || '-';
      case 'dbh': return (p.dbh_cm != null ? p.dbh_cm + ' cm' : '-');
      case 'perimeter': return (p.perimeter_cm != null ? p.perimeter_cm + ' cm' : '-');
      case 'side': return p.side || '-';
      case 'y': return (p.y_axis_m != null ? p.y_axis_m + ' m' : '-');
      default: return '#' + p.tree_id;
    }
  }

  function applyLabels() {
    markerRefs.forEach(({ marker, props }) => {
      marker.unbindTooltip();
      if (labelsOn) {
        marker.bindTooltip(String(labelText(props)), {
          permanent: true,
          direction: 'right',
          className: 'tree-label'
        });
      } else {
        const hoverText = `#${props.tree_id} (${props.species || 'Tree'}) • DBH: ${props.dbh_cm != null ? props.dbh_cm + 'cm' : '-'}`;
        marker.bindTooltip(hoverText, { direction: 'top', sticky: true, className: 'tree-label' });
      }
    });
  }

  function fitAllBounds() {
    try {
      const b = L.latLngBounds([]);
      Object.values(layers).forEach(l => l.eachLayer(x => {
        if (x.getBounds) b.extend(x.getBounds());
        else if (x.getLatLng) b.extend(x.getLatLng());
      }));
      if (b.isValid()) {
        map.fitBounds(b.pad(0.12));
      }
    } catch (e) {}
  }

  if (btnResetMapZoom) {
    btnResetMapZoom.addEventListener('click', fitAllBounds);
  }

  if (btnToggleLegend && mapLegend) {
    btnToggleLegend.addEventListener('click', () => {
      mapLegend.classList.toggle('hidden');
    });
  }
  if (btnCloseLegend && mapLegend) {
    btnCloseLegend.addEventListener('click', () => {
      mapLegend.classList.add('hidden');
    });
  }

  // --- Select & Inspect Tree ---
  function selectTree(props, lat, lon, marker) {
    selectedMarkerRef = { props, lat, lon, marker };
    layers.selection.clearLayers();

    // Add glowing selection ring
    L.circleMarker([lat, lon], {
      radius: 12,
      color: '#38bdf8',
      weight: 2.5,
      fillColor: '#38bdf8',
      fillOpacity: 0.25,
      dashArray: '3 3'
    }).addTo(layers.selection);

    // Update Sidebar Inspector
    if (inspectorBadge) {
      inspectorBadge.style.display = 'inline-block';
      inspectorBadge.textContent = `#${props.tree_id}`;
    }

    const isLeft = (props.side === 'Left' || props.side === 'left' || props.side === 'L' || props.side === 'l');
    const flagged = props.flagged === true || (props.anomalies && props.anomalies !== '-');

    if (inspectorContent) {
      inspectorContent.innerHTML = `
        <div class="inspector-detail-card">
          <div class="inspector-header-row">
            <div class="inspector-tree-title">
              <i class="fa-solid fa-tree" style="color:${flagged ? '#ef4444' : '#38bdf8'};"></i>
              <span>Tree #${props.tree_id}</span>
              <span style="font-weight:400;color:var(--text-muted);">(${props.species || 'Unknown'})</span>
            </div>
            <div>
              <span class="${isLeft ? 'side-badge-left' : 'side-badge-right'}">${props.side || 'Side N/A'}</span>
            </div>
          </div>

          <div class="inspector-grid">
            <div class="inspector-cell">
              <span class="inspector-label">DBH (Diameter)</span>
              <span class="inspector-value" style="color:#38bdf8;">
                ${props.dbh_cm != null ? props.dbh_cm + ' cm' : 'N/A'}
                ${props.dbh_derived ? '<span style="font-size:10px;color:#f59e0b;font-weight:500;">(derived)</span>' : ''}
              </span>
            </div>
            <div class="inspector-cell">
              <span class="inspector-label">Perimeter</span>
              <span class="inspector-value">${props.perimeter_cm != null ? props.perimeter_cm + ' cm' : 'N/A'}</span>
            </div>
            <div class="inspector-cell">
              <span class="inspector-label">Height Class</span>
              <span class="inspector-value">Class ${props.height_class != null ? props.height_class : '?'} <span style="font-size:10.5px;color:var(--text-muted);font-weight:400;">(${props.height_range || 'N/A'})</span></span>
            </div>
            <div class="inspector-cell">
              <span class="inspector-label">Y-Offset (Along Tape)</span>
              <span class="inspector-value">${props.y_axis_m != null ? props.y_axis_m + ' m' : 'N/A'}</span>
            </div>
          </div>

          <div class="inspector-coord-box">
            <span><strong>GPS Lat:</strong> ${lat.toFixed(6)}</span>
            <span><strong>Lon:</strong> ${lon.toFixed(6)}</span>
          </div>

          <div>
            ${flagged
              ? `<div class="tree-popup-issue"><i class="fa-solid fa-triangle-exclamation"></i> <strong>Flagged:</strong> ${props.anomalies}</div>`
              : `<div class="status-clean-tag"><i class="fa-solid fa-circle-check"></i> Quality Verified &bull; Clean Tree Record</div>`
            }
          </div>
        </div>
      `;
    }
  }

  // --- Build Popup HTML ---
  function buildPopupHtml(p, lat, lon) {
    const isLeft = (p.side === 'Left' || p.side === 'left' || p.side === 'L' || p.side === 'l');
    const flagged = p.flagged === true || (p.anomalies && p.anomalies !== '-');

    return `
      <div class="tree-popup-card">
        <div class="tree-popup-head">
          <h4><i class="fa-solid fa-tree"></i> Tree #${p.tree_id}</h4>
          <span class="${isLeft ? 'side-badge-left' : 'side-badge-right'}">${p.side || 'Side N/A'}</span>
        </div>
        <div class="tree-popup-grid">
          <div class="tree-popup-row">
            <span class="tree-popup-key">Species:</span>
            <span class="tree-popup-val">${p.species || 'Unknown'}</span>
          </div>
          <div class="tree-popup-row">
            <span class="tree-popup-key">DBH:</span>
            <span class="tree-popup-val" style="color:#38bdf8;">${p.dbh_cm != null ? p.dbh_cm + ' cm' : '-'}</span>
          </div>
          <div class="tree-popup-row">
            <span class="tree-popup-key">Perimeter:</span>
            <span class="tree-popup-val">${p.perimeter_cm != null ? p.perimeter_cm + ' cm' : '-'}</span>
          </div>
          <div class="tree-popup-row">
            <span class="tree-popup-key">Height Class:</span>
            <span class="tree-popup-val">Class ${p.height_class != null ? p.height_class : '?'}</span>
          </div>
          <div class="tree-popup-row">
            <span class="tree-popup-key">Y-offset:</span>
            <span class="tree-popup-val">${p.y_axis_m != null ? p.y_axis_m + ' m' : '-'}</span>
          </div>
          <div class="tree-popup-row">
            <span class="tree-popup-key">Derived DBH:</span>
            <span class="tree-popup-val">${p.dbh_derived ? '<span style="color:#f59e0b">Yes (&divide;&pi;)</span>' : 'No'}</span>
          </div>
        </div>
        <div style="font-size:10px;font-family:var(--font-mono);color:var(--text-muted);border-top:1px solid rgba(255,255,255,0.06);padding-top:4px;display:flex;justify-content:space-between;">
          <span>Lat: ${lat.toFixed(6)}</span>
          <span>Lon: ${lon.toFixed(6)}</span>
        </div>
        ${flagged ? `<div class="tree-popup-issue"><i class="fa-solid fa-triangle-exclamation"></i> <strong>Issue:</strong> ${p.anomalies}</div>` : ''}
      </div>
    `;
  }

  function renderGeoJSON(geojson) {
    Object.values(layers).forEach(l => l.clearLayers());
    markerRefs.length = 0;

    geojson.features.forEach(f => {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      if (f.geometry.type === 'Point') {
        const flagged = p.flagged === true || (p.anomalies && p.anomalies !== '-');
        const isLeft = (p.side === 'Left' || p.side === 'left' || p.side === 'L' || p.side === 'l');
        const color = flagged ? '#ef4444' : (isLeft ? '#1e8449' : '#1a5276');
        const radius = flagged ? 6.5 : 5.5;

        const m = L.circleMarker([lat, lon], {
          radius: radius,
          fillColor: color,
          fillOpacity: 0.9,
          color: '#ffffff',
          weight: flagged ? 2 : 1.2,
          interactive: true
        });

        m.bindPopup(buildPopupHtml(p, lat, lon), {
          maxWidth: 320,
          className: 'custom-tree-popup'
        });

        // Click event on marker
        m.on('click', (e) => {
          L.DomEvent.stopPropagation(e);
          selectTree(p, lat, lon, m);
          m.openPopup();
        });

        // Hover animation
        m.on('mouseover', () => {
          m.setRadius(radius + 2.5);
        });
        m.on('mouseout', () => {
          m.setRadius(radius);
        });

        m.addTo(flagged ? layers.flagged : layers.points);
        markerRefs.push({ marker: m, props: p, flagged, lat, lon });
      } else if (f.geometry.type === 'LineString') {
        L.polyline(f.geometry.coordinates.map(c => [c[1], c[0]]), {
          color: '#c0392b',
          weight: 4,
          dashArray: '8 6'
        }).addTo(layers.line);
      } else if (f.geometry.type === 'Polygon') {
        L.polygon(f.geometry.coordinates[0].map(c => [c[1], c[0]]), {
          color: '#a855f7',
          weight: 2,
          fillColor: '#a855f7',
          fillOpacity: 0.12,
          dashArray: '4 4'
        }).addTo(layers.boundary);
      }
    });

    applyLabels();
    fitAllBounds();
  }

  // --- process ---
  function currentBuffer() { return parseFloat(bufferRange.value); }

  function loadData() {
    const path = srcPath.value.trim();
    if (!path) {
      infoText.textContent = 'Please select or enter a source path first.';
      infoText.style.color = '#f59e0b';
      return;
    }
    state.path = path;
    state.layer = layerSel.value;
    state.deriveDbh = deriveDbh.checked;
    infoText.textContent = 'Processing and cleaning dataset...';
    infoText.style.color = '#38bdf8';
    loadBtn.disabled = true;

    fetch('/field-etl/api/process/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, layer: state.layer, derive_dbh: state.deriveDbh, buffer_m: currentBuffer() })
    }).then(r => r.json()).then(d => {
      loadBtn.disabled = false;
      if (d.status !== 'ok') {
        infoText.textContent = 'Error: ' + d.message;
        infoText.style.color = '#ef4444';
        return;
      }
      renderGeoJSON(d.geojson);
      state.stats = d.stats;
      stTotal.textContent = d.stats.total;
      stClean.textContent = d.stats.clean;
      stAnom.textContent = d.stats.anomalies;
      stDerived.textContent = d.stats.dbh_from_perimeter;
      stCrs.textContent = d.source_crs ? `CRS: ${d.source_crs}` : 'CRS: Not defined';

      if (badgeCleanCount) badgeCleanCount.textContent = d.stats.clean;
      if (badgeAnomCount) badgeAnomCount.textContent = d.stats.anomalies;

      summaryBar.classList.remove('hidden');
      infoText.textContent = `Cleaned ${d.stats.clean} / ${d.stats.total} trees (${d.stats.anomalies} anomalies flagged). Click any point on map to inspect.`;
      infoText.style.color = '#10b981';

      renderAnomalies(d.anomalies);
    }).catch(e => {
      loadBtn.disabled = false;
      infoText.textContent = 'Error: ' + e;
      infoText.style.color = '#ef4444';
    });
  }

  function renderAnomalies(items) {
    if (!items || items.length === 0) {
      if (anomCard) anomCard.style.display = 'none';
      if (anomTableWrap) anomTableWrap.innerHTML = '';
      return;
    }

    if (anomCard) anomCard.style.display = 'flex';
    if (anomListCount) anomListCount.textContent = items.length;

    let h = '<table class="data-table-mini"><thead><tr><th>Tree #</th><th>DBH</th><th>Issues (Click to Zoom &amp; Inspect)</th></tr></thead><tbody>';
    items.forEach(it => {
      h += `<tr class="flag-row" data-tree-id="${it.tree_id}">
        <td style="font-weight:700;color:#ef4444;">#${it.tree_id}</td>
        <td>${it.dbh_cm != null ? it.dbh_cm + ' cm' : '-'}</td>
        <td><span class="anom-tag">${it.anomalies.join('; ')}</span></td>
      </tr>`;
    });
    h += '</tbody></table>';
    anomTableWrap.innerHTML = h;

    // Attach click-to-zoom for anomaly rows
    anomTableWrap.querySelectorAll('.flag-row').forEach(row => {
      row.addEventListener('click', () => {
        const tid = String(row.dataset.treeId);
        const ref = markerRefs.find(r => String(r.props.tree_id) === tid);
        if (ref) {
          map.setView([ref.lat, ref.lon], 20);
          selectTree(ref.props, ref.lat, ref.lon, ref.marker);
          ref.marker.openPopup();
        }
      });
    });
  }

  // --- boundary buffer recompute ---
  let bTimer = null, bSeq = 0;
  bufferRange.addEventListener('input', () => {
    bufferVal.textContent = bufferRange.value + ' m';
    if (!state.path) return;
    clearTimeout(bTimer);
    bTimer = setTimeout(() => {
      const seq = ++bSeq;
      fetch('/field-etl/api/boundary/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: state.path, layer: state.layer, derive_dbh: state.deriveDbh, buffer_m: currentBuffer() })
      }).then(r => r.json()).then(d => {
        if (seq !== bSeq || d.status !== 'ok') return;
        layers.boundary.clearLayers();
        if (d.polygon) {
          const coords = d.polygon.geometry.coordinates[0].map(c => [c[1], c[0]]);
          L.polygon(coords, {
            color: '#a855f7',
            weight: 2,
            fillColor: '#a855f7',
            fillOpacity: 0.12,
            dashArray: '4 4'
          }).addTo(layers.boundary);
        }
      }).catch(() => {});
    }, 150);
  });

  // --- layer manager toggles ---
  document.querySelectorAll('[data-layer]').forEach(cb => {
    cb.addEventListener('change', () => {
      const name = cb.dataset.layer;
      if (cb.checked) map.addLayer(layers[name]);
      else map.removeLayer(layers[name]);
    });
  });

  showLabels.addEventListener('change', () => {
    labelsOn = showLabels.checked;
    applyLabels();
  });
  labelField.addEventListener('change', () => {
    labelMode = labelField.value;
    applyLabels();
  });

  // --- scan layers ---
  function isCsvPath(p) { return /.(csv|txt)$/i.test(p.trim()); }
  scanBtn.addEventListener('click', () => {
    const path = srcPath.value.trim();
    if (!path) return;
    if (isCsvPath(path)) {
      layerSel.innerHTML = '';
      const o = document.createElement('option');
      o.value = '';
      o.textContent = 'CSV Dataset (Single Table)';
      layerSel.appendChild(o);
      infoText.textContent = 'CSV source detected — ready to process.';
      infoText.style.color = '#38bdf8';
      return;
    }
    fetch('/field-etl/api/list-layers/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    }).then(r => r.json()).then(d => {
      if (d.status !== 'ok') {
        infoText.textContent = 'Error: ' + d.message;
        infoText.style.color = '#ef4444';
        return;
      }
      layerSel.innerHTML = '';
      d.layers.forEach(l => {
        const o = document.createElement('option');
        o.value = l;
        o.textContent = l;
        layerSel.appendChild(o);
      });
      if (d.default_layer) layerSel.value = d.default_layer;
      infoText.textContent = `${d.layers.length} vector layer(s) found.`;
      infoText.style.color = '#10b981';
    }).catch(e => {
      infoText.textContent = 'Error: ' + e;
      infoText.style.color = '#ef4444';
    });
  });

  // --- native picker ---
  pickBtn.addEventListener('click', () => {
    fetch('/field-etl/api/pick/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"type":"file"}'
    }).then(r => r.json()).then(d => {
      if (d.status === 'ok' && d.path) {
        srcPath.value = d.path;
      }
    }).catch(() => {});
  });

  loadBtn.addEventListener('click', loadData);

  // --- exports ---
  function exportUrl(kind) {
    const params = new URLSearchParams({
      path: state.path || srcPath.value.trim(),
      layer: state.layer || '',
      buffer: currentBuffer(),
      exclude: '1',
      derive_dbh: state.deriveDbh ? '1' : '0'
    });
    return ('/field-etl/export/' + kind + '/?' + params.toString());
  }

  document.getElementById('exportGpkg').addEventListener('click', () => { window.open(exportUrl('gpkg'), '_blank'); });
  document.getElementById('exportGeoJson').addEventListener('click', () => { window.open(exportUrl('geojson'), '_blank'); });
  document.getElementById('exportCsv').addEventListener('click', () => { window.open(exportUrl('csv'), '_blank'); });
})();
