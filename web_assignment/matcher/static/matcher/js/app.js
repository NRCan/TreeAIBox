/**
 * TreeToolBox Field Assignment Web Studio
 * JavaScript Application Controller
 */

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

// App State for Multi-Layer Vector Management
let map = null;
let reportMap = null;
let reportLayerGroup = null;
let layerGroupLines = null;
let layerGroupLidar = null;
let layerGroupField = null;
let layerGroupBoundary = null;  // convex hull field boundary
let currentResults = null;
let lastBounds = null;
let currentPointMarkers = [];   // Array of { marker, type: 'lidar'|'field', props, defaultTooltip }

// Multi-Layer Custom Vector Store
let customLayers = {}; // layerId -> { id, name, gdbPath, layerGroup, markers, attributes, selectedLabelField, visible, color, featureCount, bounds }
const LAYER_COLOR_PALETTE = ['#c084fc', '#34d399', '#facc15', '#f43f5e', '#38bdf8', '#818cf8', '#a78bfa', '#fb923c'];

function getNextLayerColor() {
    const count = Object.keys(customLayers).length;
    return LAYER_COLOR_PALETTE[count % LAYER_COLOR_PALETTE.length];
}

function initApp() {
    initTabs();
    initSliders();
    initMap();
    bindEvents();
    
    // Auto scan layers and CSV files on initial load
    const initialGdb = document.getElementById('gdbPath').value.trim();
    if (initialGdb) {
        scanLayers(initialGdb);
    }
    const initialCsv = document.getElementById('metricsPath').value.trim();
    if (initialCsv) {
        scanCsvs(initialCsv);
    }

    // Live boundary preview on first load (after the map is ready)
    setTimeout(() => scheduleBoundaryPreview(200), 400);
}

// ---------------------------------------------------------------------------
// Tabs Navigation
// ---------------------------------------------------------------------------
function initTabs() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            tabs.forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

            tab.classList.add('active');
            const pane = document.getElementById(target);
            if (pane) {
                pane.classList.add('active');
                if (target === 'tabMap' && map) {
                    setTimeout(() => map.invalidateSize(), 150);
                } else if (target === 'tabExecutiveReport') {
                    generateExecutiveReport();
                    setTimeout(() => {
                        let ds = currentResults;
                        const select = document.getElementById('datasetSelect');
                        const selectedId = select ? select.value : 'single';
                        if (selectedId !== '__batch__' && currentResults && currentResults.datasets && currentResults.datasets[selectedId]) {
                            ds = currentResults.datasets[selectedId];
                        }
                        if (ds && ds.geojson) {
                            ensureReportMap(ds.geojson);
                        }
                    }, 100);
                }
            }
        });
    });
}

// ---------------------------------------------------------------------------
// Live Boundary Preview (field survey area polygon)
// ---------------------------------------------------------------------------
let previewBoundaryTimer = null;

function getBoundaryPayload() {
    return {
        gdb_path: document.getElementById('gdbPath')?.value.trim() || '',
        layer: document.getElementById('layerSelect')?.value.trim() || '',
        buffer_m: parseFloat(document.getElementById('boundaryBufferSlider')?.value || '5'),
        min_height_class: document.getElementById('minHeightClass')?.value || '1',
        max_height_class: document.getElementById('maxHeightClass')?.value || '5',
        min_dbh: document.getElementById('minDbh')?.value || '',
        max_dbh: document.getElementById('maxDbh')?.value || '',
        species_filter: document.getElementById('speciesFilter')?.value.trim() || '',
    };
}

function renderBoundaryPreview(geojson) {
    if (!map || !layerGroupBoundary) return;
    layerGroupBoundary.clearLayers();
    if (!geojson || !geojson.features) return;
    geojson.features.forEach(f => {
        if (f.properties.type !== 'field_boundary') return;
        const ringCoords = f.geometry.coordinates[0];
        const latlngs = ringCoords.map(c => [c[1], c[0]]);
        const p = f.properties;
        const polygon = L.polygon(latlngs, {
            color: '#facc15',
            weight: 2,
            opacity: 0.85,
            fill: true,
            fillColor: '#fef08a',
            fillOpacity: 0.06,
            dashArray: '6 4'
        });
        polygon.bindTooltip(p.label || 'Field Boundary', { sticky: true });
        layerGroupBoundary.addLayer(polygon);
    });
}

async function previewFieldBoundary() {
    if (!document.getElementById('boundaryEnabled')?.checked) {
        if (layerGroupBoundary) layerGroupBoundary.clearLayers();
        return;
    }
    const payload = getBoundaryPayload();
    if (!payload.gdb_path) {
        if (layerGroupBoundary) layerGroupBoundary.clearLayers();
        return;
    }
    try {
        const res = await fetch('/api/boundary/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'ok') {
            renderBoundaryPreview(data.geojson);
        } else {
            if (layerGroupBoundary) layerGroupBoundary.clearLayers();
        }
    } catch (err) {
        console.error('Boundary preview error:', err);
        if (layerGroupBoundary) layerGroupBoundary.clearLayers();
    }
}

function scheduleBoundaryPreview(delayMs = 350) {
    clearTimeout(previewBoundaryTimer);
    previewBoundaryTimer = setTimeout(previewFieldBoundary, delayMs);
}

// ---------------------------------------------------------------------------
// Sliders & Weight Normalization
// ---------------------------------------------------------------------------
function initSliders() {
    const sSpatial = document.getElementById('sliderSpatial');
    const sDbh = document.getElementById('sliderDbh');
    const sHeight = document.getElementById('sliderHeight');

    function updateWeights() {
        const ws = parseFloat(sSpatial.value);
        const wd = parseFloat(sDbh.value);
        const wh = parseFloat(sHeight.value);
        const total = Math.max(ws + wd + wh, 1);

        const ps = (ws / total) * 100;
        const pd = (wd / total) * 100;
        const ph = (wh / total) * 100;

        document.getElementById('lblSpatialWeight').textContent = `${ps.toFixed(0)}% (${(ws/total).toFixed(2)})`;
        document.getElementById('lblDbhWeight').textContent = `${pd.toFixed(0)}% (${(wd/total).toFixed(2)})`;
        document.getElementById('lblHeightWeight').textContent = `${ph.toFixed(0)}% (${(wh/total).toFixed(2)})`;
    }

    sSpatial.addEventListener('input', updateWeights);
    sDbh.addEventListener('input', updateWeights);
    sHeight.addEventListener('input', updateWeights);
    updateWeights();

    // Boundary Filter controls
    const sBuffer = document.getElementById('boundaryBufferSlider');
    const chkBoundary = document.getElementById('boundaryEnabled');
    const lblBuffer = document.getElementById('lblBoundaryBuffer');
    const bufferGroup = document.getElementById('boundaryBufferGroup');
    const boundaryCard = document.getElementById('boundaryFilterCard');

    function updateBoundaryUI() {
        if (sBuffer && lblBuffer) {
            const v = parseFloat(sBuffer.value);
            lblBuffer.textContent = v.toFixed(1) + ' m';
        }
        if (bufferGroup) {
            bufferGroup.style.opacity = chkBoundary && chkBoundary.checked ? '1' : '0.4';
            bufferGroup.style.pointerEvents = chkBoundary && chkBoundary.checked ? 'auto' : 'none';
        }
    }

    if (sBuffer) {
        sBuffer.addEventListener('input', () => {
            updateBoundaryUI();
            scheduleBoundaryPreview(350);
        });
    }
    if (chkBoundary) {
        chkBoundary.addEventListener('change', () => {
            updateBoundaryUI();
            scheduleBoundaryPreview(50);
        });
    }
    updateBoundaryUI();
}

// ---------------------------------------------------------------------------
// Leaflet GIS Map Initialization
// ---------------------------------------------------------------------------
function initMap() {
    // Base tile layers with safe maxNativeZoom so deep zooms (up to 26) smoothly scale
    const esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, USDA, USGS',
        maxNativeZoom: 17,
        maxZoom: 26,
        crossOrigin: 'anonymous'
    });

    const googleSatellite = L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
        attribution: '&copy; Google Maps Satellite',
        maxNativeZoom: 18,
        maxZoom: 26,
        crossOrigin: 'anonymous'
    });

    const cartoDark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        maxNativeZoom: 18,
        maxZoom: 26,
        crossOrigin: 'anonymous'
    });

    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxNativeZoom: 18,
        maxZoom: 26,
        crossOrigin: 'anonymous'
    });

    // Create Main Studio Map
    map = L.map('gisMap', {
        center: [44.9794, -65.0859],
        zoom: 17,
        maxZoom: 26,
        layers: [esriSatellite]
    });

    // Base layer controller
    const baseMaps = {
        "ESRI Satellite": esriSatellite,
        "Google Satellite (Hybrid)": googleSatellite,
        "Carto Dark": cartoDark,
        "OpenStreetMap": osm
    };
    L.control.layers(baseMaps, null, { position: 'topright' }).addTo(map);

    // Layer groups for features
    layerGroupLines = L.layerGroup().addTo(map);
    layerGroupLidar = L.layerGroup().addTo(map);
    layerGroupField = L.layerGroup().addTo(map);
    layerGroupBoundary = L.layerGroup().addTo(map);

    // NOTE: reportMap is intentionally NOT initialized here.
    // It is initialized lazily by ensureReportMap() when the tab is first visible,
    // so Leaflet can measure a real container size.

    // Toolbar layer toggle events
    document.getElementById('chkShowLines').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(layerGroupLines);
        else map.removeLayer(layerGroupLines);
    });

    document.getElementById('chkShowLidar').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(layerGroupLidar);
        else map.removeLayer(layerGroupLidar);
    });

    document.getElementById('chkShowField').addEventListener('change', (e) => {
        if (e.target.checked) map.addLayer(layerGroupField);
        else map.removeLayer(layerGroupField);
    });

    const chkShowCustom = document.getElementById('chkShowCustom');
    if (chkShowCustom) {
        chkShowCustom.addEventListener('change', (e) => {
            Object.values(customLayers).forEach(layer => {
                layer.visible = e.target.checked;
                if (e.target.checked) map.addLayer(layer.layerGroup);
                else map.removeLayer(layer.layerGroup);
            });
            renderCustomLayersList();
            applyPointLabels();
        });
    }

    document.getElementById('btnResetMapZoom').addEventListener('click', fitMapExtents);

    // Legend toggle events
    const legend = document.getElementById('mapLegend');
    const toggleBtn = document.getElementById('btnToggleLegend');
    const closeBtn = document.getElementById('btnCloseLegend');
    if (toggleBtn && legend) {
        toggleBtn.addEventListener('click', () => legend.classList.toggle('hidden'));
    }
    if (closeBtn && legend) {
        closeBtn.addEventListener('click', () => legend.classList.add('hidden'));
    }
}

// Auto-update Output Directory based on Input Path
function updateOutputDirFromInput(inputPath) {
    if (!inputPath) return;
    const outDirInput = document.getElementById('outDir');
    if (!outDirInput) return;

    const cleanPath = inputPath.replace(/\\/g, '/').replace(/\/+$/, '');
    let baseFolder = '';

    if (cleanPath.toLowerCase().endsWith('.gdb') || /\.[a-zA-Z0-9]+$/.test(cleanPath)) {
        baseFolder = cleanPath.substring(0, cleanPath.lastIndexOf('/'));
    } else {
        baseFolder = cleanPath;
    }

    if (!baseFolder) baseFolder = cleanPath;

    if (baseFolder) {
        outDirInput.value = `${baseFolder}/field_assignment_out`;
    }
}

// Native Desktop File / Folder Picker API
async function pickPath(targetType) {
    let initialDir = '';
    if (targetType === 'gdb') {
        initialDir = document.getElementById('gdbPath')?.value.trim() || '';
    } else if (targetType === 'metrics') {
        initialDir = document.getElementById('metricsPath')?.value.trim() || '';
    } else if (targetType === 'folder') {
        initialDir = document.getElementById('outDir')?.value.trim() || '';
    }

    try {
        const res = await fetch('/api/pick-path/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: targetType, initial_dir: initialDir })
        });
        const data = await res.json();
        if (data.status === 'ok' && data.path) {
            const pickedPath = data.path;
            if (targetType === 'gdb') {
                const el = document.getElementById('gdbPath');
                if (el) el.value = pickedPath;
                scanLayers(pickedPath);
                const mPath = document.getElementById('metricsPath')?.value.trim();
                if (!mPath) updateOutputDirFromInput(pickedPath);
            } else if (targetType === 'metrics') {
                const el = document.getElementById('metricsPath');
                if (el) el.value = pickedPath;
                scanCsvs(pickedPath);
                updateOutputDirFromInput(pickedPath);
            } else if (targetType === 'folder') {
                const el = document.getElementById('outDir');
                if (el) el.value = pickedPath;
            }
        }
    } catch (err) {
        console.error('Error picking path:', err);
    }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------
function bindEvents() {
    const pickGdbBtn = document.getElementById('pickGdbBtn');
    if (pickGdbBtn) {
        pickGdbBtn.addEventListener('click', () => pickPath('gdb'));
    }

    const pickMetricsBtn = document.getElementById('pickMetricsBtn');
    if (pickMetricsBtn) {
        pickMetricsBtn.addEventListener('click', () => pickPath('metrics'));
    }

    const pickOutDirBtn = document.getElementById('pickOutDirBtn');
    if (pickOutDirBtn) {
        pickOutDirBtn.addEventListener('click', () => pickPath('folder'));
    }

    const scanLayersBtn = document.getElementById('scanLayersBtn');
    if (scanLayersBtn) {
        scanLayersBtn.addEventListener('click', () => {
            const path = document.getElementById('gdbPath')?.value.trim();
            if (path) scanLayers(path);
        });
    }

    // Re-preview the field boundary whenever the survey layer changes
    const layerSelect = document.getElementById('layerSelect');
    if (layerSelect) {
        layerSelect.addEventListener('change', () => scheduleBoundaryPreview(100));
    }

    const btnLoadCustomLayer = document.getElementById('btnLoadCustomLayer');
    if (btnLoadCustomLayer) {
        btnLoadCustomLayer.addEventListener('click', () => {
            const path = document.getElementById('gdbPath')?.value.trim();
            const layer = document.getElementById('customLayerSelect')?.value.trim();
            if (path && layer) {
                loadCustomLayer(path, layer);
            } else {
                alert('Please enter a valid GDB/SHP path and select a layer.');
            }
        });
    }

    const scanCsvsBtn = document.getElementById('scanCsvsBtn');
    if (scanCsvsBtn) {
        scanCsvsBtn.addEventListener('click', () => {
            const path = document.getElementById('metricsPath')?.value.trim();
            if (path) scanCsvs(path);
        });
    }

    // Auto-update output dir when typing or changing input paths
    const metricsPathInput = document.getElementById('metricsPath');
    if (metricsPathInput) {
        metricsPathInput.addEventListener('input', (e) => {
            updateOutputDirFromInput(e.target.value.trim());
        });
    }

    const gdbPathInput = document.getElementById('gdbPath');
    if (gdbPathInput) {
        gdbPathInput.addEventListener('input', (e) => {
            const mPath = document.getElementById('metricsPath')?.value.trim();
            if (!mPath) {
                updateOutputDirFromInput(e.target.value.trim());
            }
        });
    }

    const btnSelectAllCsvs = document.getElementById('btnSelectAllCsvs');
    if (btnSelectAllCsvs) {
        btnSelectAllCsvs.addEventListener('click', () => {
            document.querySelectorAll('#csvCheckboxList input[type="checkbox"]').forEach(cb => cb.checked = true);
        });
    }

    const btnClearAllCsvs = document.getElementById('btnClearAllCsvs');
    if (btnClearAllCsvs) {
        btnClearAllCsvs.addEventListener('click', () => {
            document.querySelectorAll('#csvCheckboxList input[type="checkbox"]').forEach(cb => cb.checked = false);
        });
    }

    const datasetSelect = document.getElementById('datasetSelect');
    if (datasetSelect) {
        datasetSelect.addEventListener('change', (e) => {
            switchActiveDataset(e.target.value);
        });
    }

    const btnRunMatch = document.getElementById('btnRunMatch');
    if (btnRunMatch) {
        btnRunMatch.addEventListener('click', runAssignment);
    }

    const tableFilterMode = document.getElementById('tableFilterMode');
    if (tableFilterMode) {
        tableFilterMode.addEventListener('change', filterTableRows);
    }

    const tableSearchInput = document.getElementById('tableSearchInput');
    if (tableSearchInput) {
        tableSearchInput.addEventListener('input', filterTableRows);
    }

    const btnCopyReport = document.getElementById('btnCopyReport');
    if (btnCopyReport) {
        btnCopyReport.addEventListener('click', () => {
            const el = document.getElementById('reportPreText');
            if (el) {
                navigator.clipboard.writeText(el.innerText).then(() => {
                    alert('Match Report Log copied to clipboard!');
                });
            }
        });
    }

    const btnExportCsv = document.getElementById('btnExportCsv');
    if (btnExportCsv) {
        btnExportCsv.addEventListener('click', () => {
            const csvPath = (currentResults && currentResults.active_csv_path) ? currentResults.active_csv_path : (currentResults ? currentResults.csv_path : null);
            if (csvPath) {
                window.location.href = `/api/download/?path=${encodeURIComponent(csvPath)}`;
            } else {
                alert('Please run the assignment first to generate the CSV table.');
            }
        });
    }

    const btnRefreshDocReport = document.getElementById('btnRefreshDocReport');
    if (btnRefreshDocReport) {
        btnRefreshDocReport.addEventListener('click', () => {
            let ds = currentResults;
            const select = document.getElementById('datasetSelect');
            const selectedId = select ? select.value : 'single';
            if (selectedId !== '__batch__' && currentResults && currentResults.datasets && currentResults.datasets[selectedId]) {
                ds = currentResults.datasets[selectedId];
            }
            if (ds && ds.geojson) {
                ensureReportMap(ds.geojson);
            }
        });
    }

    const btnPrintDoc = document.getElementById('btnPrintDoc');
    if (btnPrintDoc) {
        btnPrintDoc.addEventListener('click', printExecutiveReport);
    }

    const btnSavePdf = document.getElementById('btnSavePdf');
    if (btnSavePdf) {
        btnSavePdf.addEventListener('click', saveExecutiveReportPdf);
    }

    // Point Labels Dropdown & Field Selection
    const btnPointLabels = document.getElementById('btnPointLabels');
    const menuPointLabels = document.getElementById('menuPointLabels');
    if (btnPointLabels && menuPointLabels) {
        btnPointLabels.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = menuPointLabels.style.display === 'none';
            menuPointLabels.style.display = isHidden ? 'flex' : 'none';
        });

        document.addEventListener('click', (e) => {
            if (!document.getElementById('pointLabelDropdownWrapper')?.contains(e.target)) {
                menuPointLabels.style.display = 'none';
            }
        });

        menuPointLabels.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    document.querySelectorAll('.chk-label-field').forEach(cb => {
        cb.addEventListener('change', applyPointLabels);
    });

    document.querySelectorAll('input[name="pointLabelTarget"]').forEach(r => {
        r.addEventListener('change', applyPointLabels);
    });

    const btnClearLabels = document.getElementById('btnClearLabels');
    if (btnClearLabels) {
        btnClearLabels.addEventListener('click', () => {
            document.querySelectorAll('.chk-label-field').forEach(cb => {
                cb.checked = false;
            });
            applyPointLabels();
        });
    }
}

// ---------------------------------------------------------------------------
// Scan GDB Layers
// ---------------------------------------------------------------------------
async function scanLayers(gdbPath) {
    const layerSelect = document.getElementById('layerSelect');
    const customLayerSelect = document.getElementById('customLayerSelect');
    try {
        const res = await fetch('/api/list-layers/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gdb_path: gdbPath })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            layerSelect.innerHTML = '';
            if (customLayerSelect) {
                customLayerSelect.innerHTML = '<option value="">Select layer to view on map...</option>';
            }

            data.layers.forEach(layer => {
                const opt = document.createElement('option');
                opt.value = layer;
                opt.textContent = layer;
                if (layer === data.default_layer) opt.selected = true;
                layerSelect.appendChild(opt);

                if (customLayerSelect) {
                    const optCustom = document.createElement('option');
                    optCustom.value = layer;
                    optCustom.textContent = layer;
                    customLayerSelect.appendChild(optCustom);
                }
            });
            // After the layer list is refreshed, live-preview the field boundary
            scheduleBoundaryPreview(100);
        }
    } catch (e) {
        console.warn('Scan layers notice:', e);
    }
}

// ---------------------------------------------------------------------------
// Load & Manage Multiple Custom Vector Overlay Layers from GDB / SHP
// ---------------------------------------------------------------------------
async function loadCustomLayer(gdbPath, layerName) {
    const btn = document.getElementById('btnLoadCustomLayer');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Adding...';
    }

    try {
        const res = await fetch('/api/load-custom-layer/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gdb_path: gdbPath, layer: layerName })
        });
        const data = await res.json();

        if (data.status === 'ok' && data.geojson) {
            const layerId = `layer_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
            const layerColor = getNextLayerColor();
            const newLayerGroup = L.layerGroup().addTo(map);

            const markersList = [];
            const bounds = [];

            // Auto select a default label attribute (e.g. TreeID, Species, Name, ID, or first attribute)
            const attributes = data.attributes || [];
            let defaultLabel = '';
            if (attributes.length > 0) {
                const foundDefault = attributes.find(a => {
                    const l = a.toLowerCase();
                    return l.includes('treeid') || l.includes('species') || l.includes('name') || l === 'id';
                });
                defaultLabel = foundDefault || attributes[0];
            }

            data.geojson.features.forEach((f, idx) => {
                const c = f.geometry.coordinates;
                const latlng = [c[1], c[0]];
                bounds.push(latlng);

                const p = f.properties;
                const circle = L.circleMarker(latlng, {
                    radius: 6,
                    fillColor: layerColor,
                    color: '#ffffff',
                    weight: 1.5,
                    opacity: 1,
                    fillOpacity: 0.9
                });

                // Format popup HTML with attributes
                let popupRows = '';
                Object.keys(p).slice(0, 10).forEach(key => {
                    const val = p[key];
                    popupRows += `<div class="popup-row"><b>${key}:</b> ${val !== null ? val : 'N/A'}</div>`;
                });

                circle.bindPopup(`
                    <div class="popup-card">
                        <h4><i class="fa-solid fa-draw-polygon"></i> ${data.layer_name}</h4>
                        ${popupRows}
                    </div>
                `);

                const firstVal = Object.values(p).find(v => v !== null && v !== '');
                const defaultHover = `${data.layer_name} #${idx + 1}: ${firstVal !== undefined ? firstVal : 'Point'}`;
                circle.bindTooltip(defaultHover, { sticky: true });

                newLayerGroup.addLayer(circle);
                markersList.push({
                    marker: circle,
                    props: p,
                    defaultTooltip: defaultHover
                });
            });

            customLayers[layerId] = {
                id: layerId,
                name: data.layer_name,
                gdbPath: gdbPath,
                layerGroup: newLayerGroup,
                markers: markersList,
                attributes: attributes,
                selectedLabelField: defaultLabel,
                visible: true,
                color: layerColor,
                featureCount: data.feature_count,
                bounds: bounds
            };

            renderCustomLayersList();

            if (bounds.length > 0 && map) {
                map.fitBounds(L.latLngBounds(bounds), { padding: [40, 40] });
            }

            applyPointLabels();
        } else {
            alert('Error loading layer: ' + (data.message || 'Unknown error'));
        }
    } catch (err) {
        console.error('Error loading custom layer:', err);
        alert('Failed to load layer from vector file.');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-plus"></i> Add Layer';
        }
    }
}

function renderCustomLayersList() {
    const container = document.getElementById('customLayersListContainer');
    const countBadge = document.getElementById('customPointCount');
    if (!container) return;

    const layerKeys = Object.keys(customLayers);

    // Update toolbar total feature count
    let totalFeatures = 0;
    layerKeys.forEach(k => {
        if (customLayers[k].visible) totalFeatures += customLayers[k].featureCount;
    });
    if (countBadge) countBadge.textContent = totalFeatures;

    if (layerKeys.length === 0) {
        container.innerHTML = `
            <div class="empty-layers-notice" id="emptyCustomLayersNotice">
                <i class="fa-solid fa-circle-info"></i> Pick a layer above and click <strong>+ Add Layer</strong> to overlay vector points on the GIS map.
            </div>
        `;
        return;
    }

    container.innerHTML = '';

    layerKeys.forEach(layerId => {
        const layer = customLayers[layerId];
        const card = document.createElement('div');
        card.className = 'custom-layer-item-card';
        card.dataset.layerId = layerId;

        // Build option list for per-layer label dropdown
        let fieldOptions = `<option value="">(No labels / hover tooltips)</option>`;
        layer.attributes.forEach(attr => {
            const isSel = attr === layer.selectedLabelField ? 'selected' : '';
            fieldOptions += `<option value="${attr}" ${isSel}>${attr}</option>`;
        });

        card.innerHTML = `
            <div class="layer-item-header">
                <div class="layer-title-badge">
                    <span class="layer-color-dot" style="background-color: ${layer.color};"></span>
                    <strong class="layer-name-text" title="${layer.name}">${layer.name}</strong>
                    <span class="badge-purple">${layer.featureCount} pts</span>
                </div>
                <div class="layer-item-actions">
                    <label class="toggle-pill-sm">
                        <input type="checkbox" class="chk-layer-visible" data-layer-id="${layerId}" ${layer.visible ? 'checked' : ''}>
                        <span>Show</span>
                    </label>
                    <button type="button" class="btn-remove-layer" data-layer-id="${layerId}" title="Remove layer">&times;</button>
                </div>
            </div>
            <div class="layer-item-controls">
                <div class="form-group-xs">
                    <label><i class="fa-solid fa-tag"></i> Label Field:</label>
                    <select class="select-layer-label-field" data-layer-id="${layerId}">
                        ${fieldOptions}
                    </select>
                </div>
                <button type="button" class="btn-xs btn-outline-purple btn-zoom-layer" data-layer-id="${layerId}" title="Zoom to bounds">
                    <i class="fa-solid fa-compress"></i> Zoom
                </button>
            </div>
        `;
        container.appendChild(card);
    });

    // Wire listeners for dynamic layer controls
    container.querySelectorAll('.chk-layer-visible').forEach(chk => {
        chk.addEventListener('change', (e) => {
            const lid = e.target.dataset.layerId;
            if (customLayers[lid]) {
                customLayers[lid].visible = e.target.checked;
                if (e.target.checked) map.addLayer(customLayers[lid].layerGroup);
                else map.removeLayer(customLayers[lid].layerGroup);
                renderCustomLayersList();
                applyPointLabels();
            }
        });
    });

    container.querySelectorAll('.select-layer-label-field').forEach(sel => {
        sel.addEventListener('change', (e) => {
            const lid = e.target.dataset.layerId;
            if (customLayers[lid]) {
                customLayers[lid].selectedLabelField = e.target.value;
                applyPointLabels();
            }
        });
    });

    container.querySelectorAll('.btn-zoom-layer').forEach(btn => {
        btn.addEventListener('click', () => {
            const lid = btn.dataset.layerId;
            if (customLayers[lid] && customLayers[lid].bounds.length > 0 && map) {
                map.fitBounds(L.latLngBounds(customLayers[lid].bounds), { padding: [40, 40] });
            }
        });
    });

    container.querySelectorAll('.btn-remove-layer').forEach(btn => {
        btn.addEventListener('click', () => {
            const lid = btn.dataset.layerId;
            removeCustomLayer(lid);
        });
    });
}

function removeCustomLayer(layerId) {
    if (customLayers[layerId]) {
        if (map && map.hasLayer(customLayers[layerId].layerGroup)) {
            map.removeLayer(customLayers[layerId].layerGroup);
        }
        delete customLayers[layerId];
        renderCustomLayersList();
        applyPointLabels();
    }
}

// ---------------------------------------------------------------------------
// Scan Folder for Multiple CSV Files
// ---------------------------------------------------------------------------
async function scanCsvs(path) {
    const box = document.getElementById('csvBatchBox');
    const list = document.getElementById('csvCheckboxList');
    const title = document.getElementById('csvBatchCountTitle');

    try {
        const res = await fetch('/api/scan-csvs/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: path })
        });
        const data = await res.json();
        if (data.status === 'ok' && data.files && data.files.length > 0) {
            box.style.display = 'flex';
            list.innerHTML = '';
            title.innerHTML = `<i class="fa-solid fa-file-csv"></i> Discovered CSVs (${data.count})`;

            data.files.forEach((f, idx) => {
                const item = document.createElement('label');
                item.className = 'csv-check-item';
                item.innerHTML = `
                    <input type="checkbox" value="${f.path}" ${idx === 0 || f.is_metrics ? 'checked' : ''}>
                    <span>${f.filename}</span>
                    <span class="csv-meta-tag">${f.size_kb} KB</span>
                `;
                list.appendChild(item);
            });
        } else {
            box.style.display = 'none';
        }
    } catch (e) {
        console.warn('Scan CSVs notice:', e);
    }
}

// ---------------------------------------------------------------------------
// Run Assignment API Call (Single or Multi-CSV Batch)
// ---------------------------------------------------------------------------
async function runAssignment() {
    const btn = document.getElementById('btnRunMatch');
    const progBox = document.getElementById('progressContainer');
    const progFill = document.getElementById('progressBarFill');
    const progText = document.getElementById('progressText');

    const ws = parseFloat(document.getElementById('sliderSpatial').value);
    const wd = parseFloat(document.getElementById('sliderDbh').value);
    const wh = parseFloat(document.getElementById('sliderHeight').value);
    const total = Math.max(ws + wd + wh, 1);

    // Collect selected CSV files from batch checkbox list if visible
    const checkedCsvs = [];
    document.querySelectorAll('#csvCheckboxList input[type="checkbox"]:checked').forEach(cb => {
        checkedCsvs.push(cb.value);
    });

    const metricsPathInput = document.getElementById('metricsPath').value.trim();

    const payload = {
        gdb_path: document.getElementById('gdbPath').value.trim(),
        layer: document.getElementById('layerSelect').value.trim(),
        metrics_path: metricsPathInput,
        metrics_paths: checkedCsvs.length > 0 ? checkedCsvs : null,
        out_dir: document.getElementById('outDir').value.trim(),
        tolerance: parseFloat(document.getElementById('tolerance').value),
        dbh_scale: parseFloat(document.getElementById('dbhScale').value),
        weight_spatial: ws / total,
        weight_dbh: wd / total,
        weight_height: wh / total,
        method: document.getElementById('solverMethod').value,

        // Boundary Filter (field survey area clip)
        boundary_enabled: document.getElementById('boundaryEnabled').checked,
        boundary_buffer_m: parseFloat(document.getElementById('boundaryBufferSlider').value),

        // Exclusion filters
        min_height_class: document.getElementById('minHeightClass').value,
        max_height_class: document.getElementById('maxHeightClass').value,
        min_dbh: document.getElementById('minDbh').value,
        max_dbh: document.getElementById('maxDbh').value,
        species_filter: document.getElementById('speciesFilter').value.trim(),
    };

    if (!payload.gdb_path) {
        alert('Please enter a valid Field Survey file path.');
        return;
    }
    if (!payload.metrics_paths && !payload.metrics_path) {
        alert('Please enter or select at least one LiDAR metrics CSV.');
        return;
    }

    // UI Loading state
    btn.disabled = true;
    progBox.style.display = 'flex';
    progFill.style.width = '25%';
    progText.textContent = checkedCsvs.length > 1 ? `Batch processing ${checkedCsvs.length} LiDAR CSV files...` : 'Optimizing matching model...';

    try {
        const response = await fetch('/api/run-match/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        progFill.style.width = '75%';

        const result = await response.json();
        if (result.status !== 'ok') {
            throw new Error(result.message || 'Execution error');
        }

        progFill.style.width = '100%';
        progText.textContent = 'Rendering GIS map & analytics...';

        currentResults = result;

        // Setup Dataset Switcher & Batch Tab
        setupDatasetSwitcher(result);

        // Render Active Dataset
        if (result.is_batch && result.datasets) {
            renderBatchComparison(result.batch_summary);
            const firstId = result.active_id || Object.keys(result.datasets)[0];
            switchActiveDataset(firstId, Boolean(lastBounds));
        } else {
            document.getElementById('tabBatchBtn').style.display = 'none';
            document.getElementById('batchBadge').style.display = 'none';
            renderDashboard(result);
            renderMapFeatures(result.geojson, Boolean(lastBounds));
            renderTable(result.table_rows);
            renderConfusionMatrix(result.confusion_matrix);
            renderReport(result.report_text);
        }

        progText.textContent = 'Complete!';
        setTimeout(() => {
            progBox.style.display = 'none';
            btn.disabled = false;
        }, 600);

    } catch (err) {
        alert(`Assignment failed:\n\n${err.message}`);
        btn.disabled = false;
        progBox.style.display = 'none';
    }
}

// ---------------------------------------------------------------------------
// Setup Dataset Switcher Dropdown
// ---------------------------------------------------------------------------
function setupDatasetSwitcher(result) {
    const select = document.getElementById('datasetSelect');
    const batchBadge = document.getElementById('batchBadge');
    const batchBtn = document.getElementById('tabBatchBtn');

    select.innerHTML = '';

    if (result.is_batch && result.datasets) {
        const dsKeys = Object.keys(result.datasets);
        batchBadge.style.display = 'inline-block';
        batchBadge.textContent = `${dsKeys.length} CSVs`;
        batchBtn.style.display = 'flex';

        // Add Batch Overview Option
        const optBatch = document.createElement('option');
        optBatch.value = '__batch__';
        optBatch.textContent = `📊 Compare All (${dsKeys.length} Datasets)`;
        select.appendChild(optBatch);

        // Add each individual dataset option
        dsKeys.forEach((key, idx) => {
            const ds = result.datasets[key];
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = `📄 ${ds.filename} (${ds.summary.matched_count}/${ds.summary.total_field} field matched, ${ds.summary.field_match_rate}%)`;
            if (idx === 0) opt.selected = true;
            select.appendChild(opt);
        });

    } else {
        batchBadge.style.display = 'none';
        batchBtn.style.display = 'none';
        const opt = document.createElement('option');
        opt.value = 'single';
        opt.textContent = result.summary && result.summary.filename ? `📄 ${result.summary.filename}` : '📄 Single Dataset';
        opt.selected = true;
        select.appendChild(opt);
    }
}

// ---------------------------------------------------------------------------
// Switch Active Dataset in Web UI
// ---------------------------------------------------------------------------
function switchActiveDataset(datasetId, preserveView = false) {
    if (!currentResults) return;

    if (datasetId === '__batch__') {
        // Activate Batch Comparison Tab
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        const batchBtn = document.getElementById('tabBatchBtn');
        const batchPane = document.getElementById('tabBatch');
        if (batchBtn) batchBtn.classList.add('active');
        if (batchPane) batchPane.classList.add('active');
        return;
    }

    let ds = currentResults;
    if (currentResults.datasets && currentResults.datasets[datasetId]) {
        ds = currentResults.datasets[datasetId];
        currentResults.active_csv_path = ds.csv_path;
    }

    renderDashboard(ds);
    renderMapFeatures(ds.geojson, preserveView);
    renderTable(ds.table_rows);
    renderConfusionMatrix(ds.confusion_matrix);
    renderReport(ds.report_text);
    generateExecutiveReport();
}

// ---------------------------------------------------------------------------
// Render Multi-CSV Batch Comparison Matrix
// ---------------------------------------------------------------------------
function renderBatchComparison(batchList) {
    const tbody = document.getElementById('batchTableBody');
    const countText = document.getElementById('batchTotalCountText');
    tbody.innerHTML = '';

    if (!batchList || batchList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="empty-state">No batch evaluation data available.</td></tr>`;
        return;
    }

    countText.textContent = `${batchList.length} Datasets Evaluated`;

    batchList.forEach(b => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight: 700; color: #38bdf8;"><i class="fa-solid fa-file-csv"></i> ${b.filename}</td>
            <td>${b.total_lidar}</td>
            <td style="font-weight: 700; color: #34d399;">${b.matched_count}</td>
            <td><span class="badge-tag badge-matched">${b.lidar_match_rate}%</span></td>
            <td>${b.field_match_rate}%</td>
            <td>${b.mean_distance_m !== null ? b.mean_distance_m + ' m' : '-'}</td>
            <td>${b.dbh_mae_cm !== null ? b.dbh_mae_cm + ' cm' : '-'}</td>
            <td>${b.dbh_corr !== null ? b.dbh_corr : '-'}</td>
            <td>
                <button type="button" class="btn-sm btn-outline btn-view-single" data-id="${b.id}">
                    <i class="fa-solid fa-eye"></i> View Results
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    // Wire view buttons in batch table
    tbody.querySelectorAll('.btn-view-single').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.dataset.id;
            const select = document.getElementById('datasetSelect');
            if (select) select.value = id;
            switchActiveDataset(id);
            // Switch to Map tab
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            document.querySelector('.nav-tab[data-tab="tabMap"]').classList.add('active');
            document.getElementById('tabMap').classList.add('active');
            if (map) setTimeout(() => map.invalidateSize(), 150);
        });
    });
}

// ---------------------------------------------------------------------------
// Render Dashboard Cards
// ---------------------------------------------------------------------------
function renderDashboard(data) {
    const s = data.summary;
    // Primary match rate is now based on Ground Truth Field Survey trees
    document.getElementById('valMatchRate').textContent = `${s.matched_count} / ${s.total_field} (${s.field_match_rate}%)`;
    const clipInfo = (s.lidar_clipped_out > 0) ? ` • ⚠️ ${s.lidar_clipped_out} LiDAR outside boundary` : '';
    document.getElementById('valMatchRateSub').textContent = `Field Recovery: ${s.field_match_rate}% | LiDAR Precision: ${s.lidar_match_rate}%${clipInfo} (${s.matched_count}/${s.total_lidar} trees)`;

    document.getElementById('valDistErr').textContent = s.mean_distance_m !== null ? `${s.mean_distance_m} m` : 'N/A';
    document.getElementById('valDistMedian').textContent = s.median_distance_m !== null ? `Median: ${s.median_distance_m} m` : '';

    if (s.dbh_mae_cm !== null && s.dbh_rmse_cm !== null) {
        document.getElementById('valDbhError').textContent = `${s.dbh_mae_cm} / ${s.dbh_rmse_cm} cm`;
    } else {
        document.getElementById('valDbhError').textContent = 'N/A';
    }

    document.getElementById('valDbhCorr').textContent = s.dbh_corr !== null ? `${s.dbh_corr}` : 'N/A';
}

// ---------------------------------------------------------------------------
// Render GeoJSON Map Features
// ---------------------------------------------------------------------------
function renderMapFeatures(geojson, preserveView = false) {
    if (!geojson || !map) return;

    // Capture current view before clearing layers if user requested preservation
    const currentCenter = preserveView ? map.getCenter() : null;
    const currentZoom = preserveView ? map.getZoom() : null;

    layerGroupLines.clearLayers();
    layerGroupLidar.clearLayers();
    layerGroupField.clearLayers();
    if (layerGroupBoundary) layerGroupBoundary.clearLayers();
    currentPointMarkers = [];

    const bounds = [];

    geojson.features.forEach(f => {
        const type = f.properties.type;

        if (type === 'match_line') {
            const coords = f.geometry.coordinates; // [[lon1, lat1], [lon2, lat2]]
            const latlngs = coords.map(c => [c[1], c[0]]);
            bounds.push(latlngs[0], latlngs[1]);

            const p = f.properties;
            const line = L.polyline(latlngs, {
                color: p.score >= 0.7 ? '#10b981' : (p.score >= 0.5 ? '#f59e0b' : '#f43f5e'),
                weight: 3,
                opacity: 0.85,
                dashArray: p.distance_m > 1.5 ? '4, 4' : null
            });

            line.bindTooltip(`Match: LiDAR #${p.lidar_id} ↔ Field #${p.field_id} | ${p.distance_m}m | Score: ${p.score}`, {
                sticky: true
            });

            line.bindPopup(`
                <div class="popup-card">
                    <h4><i class="fa-solid fa-link"></i> Matched Connection</h4>
                    <div class="popup-row"><b>LiDAR Tree ID:</b> ${p.lidar_id}</div>
                    <div class="popup-row"><b>Field Tag ID:</b> ${p.field_id}</div>
                    <div class="popup-row"><b>Spatial Distance:</b> ${p.distance_m} m</div>
                    <div class="popup-row"><b>Confidence Score:</b> ${p.score}</div>
                    <div class="popup-row"><b>LiDAR DBH:</b> ${p.lidar_dbh || 'N/A'} cm</div>
                    <div class="popup-row"><b>Field DBH:</b> ${p.field_dbh || 'N/A'} cm</div>
                    <div class="popup-row"><b>Height Class:</b> LiDAR ${p.lidar_class} vs Field ${p.field_class}</div>
                    <div class="popup-row"><b>Species:</b> ${p.species || 'N/A'}</div>
                </div>
            `);

            layerGroupLines.addLayer(line);

        } else if (type === 'lidar_point') {
            const c = f.geometry.coordinates;
            const latlng = [c[1], c[0]];
            bounds.push(latlng);

            const p = f.properties;
            const circle = L.circleMarker(latlng, {
                radius: 6,
                fillColor: '#38bdf8',
                color: '#ffffff',
                weight: 1.5,
                opacity: 1,
                fillOpacity: 0.9
            });

            const defaultHover = `LiDAR #${p.tree_id}: ${p.height_m || 0}m, ${p.dbh_cm || 0}cm DBH`;
            circle.bindTooltip(defaultHover, { sticky: true });

            circle.bindPopup(`
                <div class="popup-card">
                    <h4><i class="fa-solid fa-cloud"></i> LiDAR Extracted Tree</h4>
                    <div class="popup-row"><b>LiDAR ID:</b> ${p.tree_id}</div>
                    <div class="popup-row"><b>Height:</b> ${p.height_m || 'N/A'} m (Class ${p.height_class})</div>
                    <div class="popup-row"><b>DBH:</b> ${p.dbh_cm || 'N/A'} cm</div>
                    <div class="popup-row"><b>Volume:</b> ${p.volume_m3 || 'N/A'} m³</div>
                    <div class="popup-row"><b>Points:</b> ${p.n_points}</div>
                </div>
            `);

            layerGroupLidar.addLayer(circle);

            currentPointMarkers.push({
                marker: circle,
                type: 'lidar',
                props: p,
                defaultTooltip: defaultHover
            });

        } else if (type === 'field_point') {
            const c = f.geometry.coordinates;
            const latlng = [c[1], c[0]];
            bounds.push(latlng);

            const p = f.properties;
            const circle = L.circleMarker(latlng, {
                radius: 6,
                fillColor: '#fb923c',
                color: '#ffffff',
                weight: 1.5,
                opacity: 1,
                fillOpacity: 0.9
            });

            const defaultHover = `Field Tag #${p.field_id}: ${p.species || 'Tree'}, Class ${p.height_class}`;
            circle.bindTooltip(defaultHover, { sticky: true });

            circle.bindPopup(`
                <div class="popup-card">
                    <h4><i class="fa-solid fa-location-dot"></i> Field Survey Tree</h4>
                    <div class="popup-row"><b>Field Tag ID:</b> ${p.field_id}</div>
                    <div class="popup-row"><b>Height Class:</b> Class ${p.height_class} (${p.height_range})</div>
                    <div class="popup-row"><b>DBH:</b> ${p.dbh_cm || 'N/A'} cm</div>
                    <div class="popup-row"><b>Species:</b> ${p.species || 'N/A'}</div>
                    <div class="popup-row"><b>Crown Class:</b> ${p.crown_class || 'N/A'}</div>
                </div>
            `);

            layerGroupField.addLayer(circle);

            currentPointMarkers.push({
                marker: circle,
                type: 'field',
                props: p,
                defaultTooltip: defaultHover
            });
        } else if (type === 'field_boundary') {
            // Convex hull boundary of field survey area — shown as dashed perimeter
            const ringCoords = f.geometry.coordinates[0];
            const latlngs = ringCoords.map(c => [c[1], c[0]]);
            bounds.push(...latlngs);
            const p = f.properties;
            const polygon = L.polygon(latlngs, {
                color: '#facc15',
                weight: 2,
                opacity: 0.85,
                fill: true,
                fillColor: '#fef08a',
                fillOpacity: 0.06,
                dashArray: '6 4'
            });
            polygon.bindTooltip(
                `Field Survey Boundary | ${p.lidar_raw} raw → ${p.lidar_after_clip} clipped LiDAR (removed: ${p.lidar_clipped_out})`,
                { sticky: true }
            );
            layerGroupBoundary.addLayer(polygon);
        }
    });

    applyPointLabels();

    if (bounds.length > 0) {
        lastBounds = bounds;
        if (preserveView && currentCenter && currentZoom) {
            // Keep user's exact zoom and center position without resetting
            map.setView(currentCenter, currentZoom, { animate: false });
        } else {
            map.fitBounds(L.latLngBounds(bounds), { padding: [40, 40] });
        }
    }
}

// ---------------------------------------------------------------------------
// Apply Dynamic Multi-Field Point Labels
// ---------------------------------------------------------------------------
function applyPointLabels() {
    const checkedBoxes = Array.from(document.querySelectorAll('.chk-label-field:checked')).map(cb => cb.value);
    const target = document.querySelector('input[name="pointLabelTarget"]:checked')?.value || 'all';
    const customAttrField = document.getElementById('customLabelFieldSelect')?.value;

    const hasCheckedLabels = checkedBoxes.length > 0;
    const hasCustomLabel = !!customAttrField;

    // Update badge & button state
    const badge = document.getElementById('labelCountBadge');
    const btn = document.getElementById('btnPointLabels');
    if (badge) {
        if (hasCheckedLabels) {
            badge.textContent = checkedBoxes.length;
            badge.style.display = 'inline-block';
            btn?.classList.add('active-filter');
        } else {
            badge.style.display = 'none';
            btn?.classList.remove('active-filter');
        }
    }

    // Process LiDAR & Field markers
    if (currentPointMarkers && currentPointMarkers.length > 0) {
        currentPointMarkers.forEach(item => {
            const isTargetMatch = (target === 'all') || (target === item.type);

            if (!hasCheckedLabels || !isTargetMatch) {
                // Revert to standard hover tooltip
                item.marker.unbindTooltip();
                item.marker.bindTooltip(item.defaultTooltip, { sticky: true });
                return;
            }

            // Build formatted label parts
            const parts = [];
            const p = item.props;
            checkedBoxes.forEach(field => {
                if (field === 'id') {
                    const idVal = (item.type === 'lidar') ? p.tree_id : p.field_id;
                    if (idVal !== undefined && idVal !== null) parts.push(`#${idVal}`);
                } else if (field === 'dbh') {
                    if (p.dbh_cm !== undefined && p.dbh_cm !== null) parts.push(`${p.dbh_cm}cm`);
                } else if (field === 'height_class') {
                    if (p.height_class !== undefined && p.height_class !== null) parts.push(`Cl:${p.height_class}`);
                } else if (field === 'height') {
                    if (item.type === 'lidar' && p.height_m !== undefined && p.height_m !== null) {
                        parts.push(`${p.height_m}m`);
                    } else if (item.type === 'field' && p.height_range) {
                        parts.push(p.height_range);
                    }
                } else if (field === 'species') {
                    if (p.species && p.species !== '-') parts.push(p.species);
                } else if (field === 'volume') {
                    if (p.volume_m3 !== undefined && p.volume_m3 !== null) parts.push(`${p.volume_m3}m³`);
                }
            });

            if (parts.length === 0) {
                item.marker.unbindTooltip();
                item.marker.bindTooltip(item.defaultTooltip, { sticky: true });
                return;
            }

            const labelText = parts.join(' | ');
            item.marker.unbindTooltip();
            item.marker.bindTooltip(labelText, {
                permanent: true,
                direction: 'top',
                className: `map-point-label map-point-label-${item.type}`,
                offset: [0, -6]
            }).openTooltip();
        });
    }

    // Process Custom Layer Point Markers for all loaded custom layers
    Object.values(customLayers).forEach(layer => {
        if (!layer.markers) return;

        const isTargetMatch = (target === 'all') || (target === 'custom');
        const selectedField = layer.selectedLabelField;

        layer.markers.forEach(item => {
            if (!layer.visible || !isTargetMatch || !selectedField) {
                item.marker.unbindTooltip();
                item.marker.bindTooltip(item.defaultTooltip, { sticky: true });
                return;
            }

            const p = item.props;
            const val = p[selectedField];
            if (val !== undefined && val !== null && val !== '') {
                const labelText = `${selectedField}: ${val}`;
                item.marker.unbindTooltip();
                item.marker.bindTooltip(labelText, {
                    permanent: true,
                    direction: 'top',
                    className: 'map-point-label map-point-label-custom',
                    offset: [0, -6]
                }).openTooltip();
            } else {
                item.marker.unbindTooltip();
                item.marker.bindTooltip(item.defaultTooltip, { sticky: true });
            }
        });
    });
}

function fitMapExtents() {
    if (!map) return;
    const allLayers = [];
    if (layerGroupLines) layerGroupLines.eachLayer(l => allLayers.push(l));
    if (layerGroupLidar) layerGroupLidar.eachLayer(l => allLayers.push(l));
    if (layerGroupField) layerGroupField.eachLayer(l => allLayers.push(l));
    Object.values(customLayers).forEach(layer => {
        if (layer.visible && layer.layerGroup) {
            layer.layerGroup.eachLayer(l => allLayers.push(l));
        }
    });

    if (allLayers.length > 0) {
        const group = L.featureGroup(allLayers);
        map.fitBounds(group.getBounds(), { padding: [40, 40] });
    }
}

function fitReportMapExtents() {
    if (!reportMap) return;
    if (lastBounds && lastBounds.length > 0) {
        reportMap.fitBounds(L.latLngBounds(lastBounds), { padding: [30, 30] });
    } else if (reportLayerGroup) {
        const layers = [];
        reportLayerGroup.eachLayer(l => layers.push(l));
        if (layers.length > 0) {
            reportMap.fitBounds(L.featureGroup(layers).getBounds(), { padding: [30, 30] });
        }
    }
}

// ---------------------------------------------------------------------------
// Render Results Table
// ---------------------------------------------------------------------------
function renderTable(rows) {
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    if (!rows || rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="empty-state">No tree records returned.</td></tr>`;
        return;
    }

    rows.forEach(r => {
        const tr = document.createElement('tr');
        tr.dataset.status = r.status;
        tr.dataset.lidarId = r.lidar_id !== null ? r.lidar_id : '';
        tr.dataset.fieldId = r.field_id !== null ? r.field_id : '';

        const badgeHtml = r.status === 'matched' 
            ? `<span class="badge-tag badge-matched"><i class="fa-solid fa-check"></i> Matched</span>`
            : `<span class="badge-tag badge-unmatched"><i class="fa-solid fa-xmark"></i> Unmatched</span>`;

        tr.innerHTML = `
            <td style="font-weight: 600; color: ${r.lidar_id ? '#38bdf8' : '#9ca3af'};">${r.lidar_id !== null ? r.lidar_id : '(Unmatched)'}</td>
            <td style="font-weight: 600; color: ${r.field_id ? '#fb923c' : '#9ca3af'};">${r.field_id !== null ? r.field_id : '(Unmatched)'}</td>
            <td>${r.distance_m !== null ? r.distance_m + ' m' : '-'}</td>
            <td style="font-weight: 600;">${r.score !== null ? r.score : '-'}</td>
            <td>${r.lidar_dbh_cm !== null ? r.lidar_dbh_cm : '-'}</td>
            <td>${r.field_dbh_cm !== null ? r.field_dbh_cm : '-'}</td>
            <td style="color: ${r.dbh_diff_cm > 0 ? '#38bdf8' : '#9ca3af'};">${r.dbh_diff_cm !== null ? (r.dbh_diff_cm > 0 ? '+' : '') + r.dbh_diff_cm : '-'}</td>
            <td>${r.lidar_height_class !== null ? r.lidar_height_class : '-'}</td>
            <td>${r.field_height_class !== null ? r.field_height_class : '-'}</td>
            <td>${r.species || '-'}</td>
            <td>${badgeHtml}</td>
        `;
        tbody.appendChild(tr);
    });

    filterTableRows();
}

function filterTableRows() {
    const mode = document.getElementById('tableFilterMode').value;
    const query = document.getElementById('tableSearchInput').value.trim().toLowerCase();
    const rows = document.querySelectorAll('#tableBody tr');

    rows.forEach(row => {
        const status = row.dataset.status;
        let show = true;

        if (mode === 'matched' && status !== 'matched') show = false;
        else if (mode === 'unmatched_lidar' && status !== 'unmatched_lidar') show = false;
        else if (mode === 'unmatched_field' && status !== 'unmatched_field') show = false;

        if (show && query) {
            const text = row.innerText.toLowerCase();
            if (!text.includes(query)) show = false;
        }

        row.style.display = show ? '' : 'none';
    });
}

// ---------------------------------------------------------------------------
// Render Confusion Matrix
// ---------------------------------------------------------------------------
function renderConfusionMatrix(matrix) {
    const tbody = document.getElementById('matrixBody');
    tbody.innerHTML = '';
    if (!matrix) return;

    for (let r = 0; r < 5; r++) {
        const tr = document.createElement('tr');
        let rowHtml = `<th style="text-align: left;">Field Class ${r + 1}</th>`;
        for (let c = 0; c < 5; c++) {
            const val = matrix[r][c];
            const isDiag = (r === c && val > 0);
            rowHtml += `<td class="${isDiag ? 'cell-diag' : ''}">${val}</td>`;
        }
        tr.innerHTML = rowHtml;
        tbody.appendChild(tr);
    }
}

// ---------------------------------------------------------------------------
// Render Report Log
// ---------------------------------------------------------------------------
function renderReport(text) {
    const pre = document.getElementById('reportPreText');
    pre.textContent = text || 'Report unavailable.';
}

// ---------------------------------------------------------------------------
// Executive Audit Report Compilation
// ---------------------------------------------------------------------------
function generateExecutiveReport() {
    if (!currentResults) return;

    let ds = currentResults;
    const select = document.getElementById('datasetSelect');
    const selectedId = select ? select.value : 'single';
    if (selectedId !== '__batch__' && currentResults.datasets && currentResults.datasets[selectedId]) {
        ds = currentResults.datasets[selectedId];
    }

    const s = ds.summary || {};

    // Header metadata
    document.getElementById('docGeneratedDate').textContent = new Date().toLocaleString();
    document.getElementById('docActiveDatasetName').textContent = s.filename || 'Single Dataset';
    document.getElementById('reportDatasetTag').textContent = `Dataset: ${s.filename || 'Single Run'}`;

    // Section 1: KPIs
    document.getElementById('docFieldMatchRate').textContent = `${s.field_match_rate !== undefined ? s.field_match_rate : '--'}%`;
    document.getElementById('docFieldMatchCounts').textContent = `${s.matched_count || 0} / ${s.total_field || 0} Surveyed Trees`;

    document.getElementById('docLidarMatchRate').textContent = `${s.lidar_match_rate !== undefined ? s.lidar_match_rate : '--'}%`;
    const clipNote = (s.lidar_clipped_out > 0)
        ? ` (${s.total_lidar_raw} raw → ${s.lidar_clipped_out} outside boundary removed)`
        : '';
    document.getElementById('docLidarMatchCounts').textContent = `${s.matched_count || 0} / ${s.total_lidar || 0} LiDAR Trees${clipNote}`;

    document.getElementById('docMeanDist').textContent = s.mean_distance_m !== null ? `${s.mean_distance_m} m` : 'N/A';
    document.getElementById('docMedianDist').textContent = s.median_distance_m !== null ? `Median: ${s.median_distance_m} m` : '';

    if (s.dbh_mae_cm !== null && s.dbh_rmse_cm !== null) {
        document.getElementById('docDbhErrors').textContent = `${s.dbh_mae_cm} / ${s.dbh_rmse_cm} cm`;
    } else {
        document.getElementById('docDbhErrors').textContent = 'N/A';
    }
    document.getElementById('docDbhCorr').textContent = s.dbh_corr !== null ? `Pearson r: ${s.dbh_corr}` : 'Pearson r: N/A';

    // Section 2: Parameters Audit
    document.getElementById('docParamGdb').textContent = document.getElementById('gdbPath').value.trim() || '-';
    document.getElementById('docParamLayer').textContent = document.getElementById('layerSelect').value.trim() || '-';
    document.getElementById('docParamSolver').textContent = document.getElementById('solverMethod').value === 'optimal' ? 'Hungarian Algorithm (Global Optimum)' : 'Greedy Nearest-First';
    document.getElementById('docParamLiDAR').textContent = s.path || document.getElementById('metricsPath').value.trim() || '-';
    document.getElementById('docParamTol').textContent = `${document.getElementById('tolerance').value} m`;
    document.getElementById('docParamDbhScale').textContent = `${document.getElementById('dbhScale').value} cm`;

    const ws = document.getElementById('lblSpatialWeight').textContent;
    const wd = document.getElementById('lblDbhWeight').textContent;
    const wh = document.getElementById('lblHeightWeight').textContent;
    document.getElementById('docParamWeights').textContent = `Spatial: ${ws} | DBH: ${wd} | Height: ${wh}`;

    const minHc = document.getElementById('minHeightClass').value;
    const maxHc = document.getElementById('maxHeightClass').value;
    const minD = document.getElementById('minDbh').value || 'None';
    const maxD = document.getElementById('maxDbh').value || 'None';
    const sp = document.getElementById('speciesFilter').value.trim() || 'All Species';
    document.getElementById('docParamFilters').textContent = `Height Class: ${minHc} to ${maxHc} | Min DBH: ${minD} cm | Max DBH: ${maxD} cm | Species: ${sp}`;

    // Section 4: Confusion Matrix
    const matrixBody = document.getElementById('docMatrixBody');
    matrixBody.innerHTML = '';
    const m = ds.confusion_matrix;
    if (m) {
        for (let r = 0; r < 5; r++) {
            const tr = document.createElement('tr');
            let rowHtml = `<th class="doc-matrix-header-cell">Field Class ${r + 1}</th>`;
            for (let c = 0; c < 5; c++) {
                const val = m[r][c];
                const isDiag = (r === c && val > 0);
                const isMismatch = (r !== c && val > 0);
                
                let cellClass = 'doc-matrix-cell';
                if (isDiag) cellClass += ' doc-matrix-match';
                else if (isMismatch) cellClass += ' doc-matrix-mismatch';
                else cellClass += ' doc-matrix-zero';

                rowHtml += `<td class="${cellClass}">${val}</td>`;
            }
            tr.innerHTML = rowHtml;
            matrixBody.appendChild(tr);
        }
    }

    // Section 5: Matched Inventory Table (Top 26 on Page 3)
    const invBody = document.getElementById('docInventoryTableBody');
    invBody.innerHTML = '';
    const rows = (ds.table_rows || []).filter(r => r.status === 'matched');
    if (rows.length === 0) {
        invBody.innerHTML = `<tr><td colspan="10" class="empty-state">No matched tree records found.</td></tr>`;
    } else {
        rows.slice(0, 26).forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight: 700; color: #0284c7;">${r.lidar_id !== null ? r.lidar_id : '-'}</td>
                <td style="font-weight: 700; color: #ea580c;">${r.field_id !== null ? r.field_id : '-'}</td>
                <td>${r.distance_m !== null ? r.distance_m : '-'}</td>
                <td style="font-weight: 600;">${r.score !== null ? r.score : '-'}</td>
                <td>${r.lidar_dbh_cm !== null ? r.lidar_dbh_cm : '-'}</td>
                <td>${r.field_dbh_cm !== null ? r.field_dbh_cm : '-'}</td>
                <td style="${r.dbh_diff_cm !== null ? (Math.abs(r.dbh_diff_cm) > 10 ? 'color: #dc2626;' : 'color: #16a34a;') : ''}">${r.dbh_diff_cm !== null ? (r.dbh_diff_cm > 0 ? '+' + r.dbh_diff_cm : r.dbh_diff_cm) : '-'}</td>
                <td>Class ${r.lidar_height_class || '-'}</td>
                <td>Class ${r.field_height_class || '-'}</td>
                <td>${r.species || '-'}</td>
            `;
            invBody.appendChild(tr);
        });
    }

    // Section 6: Batch Table if Multi-Dataset (Page 4)
    const batchSec = document.getElementById('docBatchSection');
    const batchBody = document.getElementById('docBatchTableBody');
    if (currentResults.is_batch && currentResults.batch_summary && currentResults.batch_summary.length > 1) {
        batchSec.style.display = 'block';
        batchBody.innerHTML = '';
        currentResults.batch_summary.forEach(b => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="doc-cell-filename" style="font-weight: 700; color: #0284c7; font-size: 9.5px; line-height: 1.35; padding: 6px 8px; word-break: break-word; overflow-wrap: anywhere; text-align: left;">${b.filename}</td>
                <td>${b.total_lidar}</td>
                <td style="font-weight: 700; color: #16a34a;">${b.matched_count}</td>
                <td>${b.field_match_rate}%</td>
                <td>${b.lidar_match_rate}%</td>
                <td>${b.mean_distance_m !== null ? b.mean_distance_m + ' m' : '-'}</td>
                <td>${b.dbh_mae_cm !== null ? b.dbh_mae_cm + ' cm' : '-'}</td>
                <td>${b.dbh_corr !== null ? b.dbh_corr : '-'}</td>
            `;
            batchBody.appendChild(tr);
        });
    } else {
        batchSec.style.display = 'none';
    }

    // Section 7: Audit Log — render each line as its own div so PDF never splits mid-line
    const logEl = document.getElementById('docRawLogText');
    const logText = ds.report_text || 'Report unavailable.';
    const logLines = logText.split('\n');
    logEl.innerHTML = logLines.map(line =>
        `<div style="break-inside:avoid;page-break-inside:avoid;white-space:pre-wrap;word-break:break-all;overflow-wrap:anywhere;min-height:1em;">${line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') || ' '}</div>`
    ).join('');
}

// ---------------------------------------------------------------------------
// Report Map: Pure SVG Renderer (no second Leaflet instance needed)
// Projects GeoJSON coordinates to SVG viewport — always renders regardless of tab visibility
// ---------------------------------------------------------------------------
function ensureReportMap(geojson) {
    const container = document.getElementById('docReportLiveMap');
    if (!container || !geojson || !geojson.features) return;

    // Use fixed standard A4 content dimensions (700 x 350) matching container height
    // so SVG viewport spans 100% of container width and height without any whitespace gaps
    const W = 700;
    const H = 350;

    // Collect all coordinates to compute geographic bounding box
    const lons = [], lats = [];
    geojson.features.forEach(f => {
        const coords = f.geometry.coordinates;
        if (f.geometry.type === 'LineString') {
            coords.forEach(c => { lons.push(c[0]); lats.push(c[1]); });
        } else if (f.geometry.type === 'Point') {
            lons.push(coords[0]); lats.push(coords[1]);
        } else if (f.geometry.type === 'Polygon') {
            coords[0].forEach(c => { lons.push(c[0]); lats.push(c[1]); });
        }
    });

    if (lons.length === 0) return;

    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);

    const PAD = 25;
    const avgLat = (minLat + maxLat) / 2;
    const cosLat = Math.cos(avgLat * Math.PI / 180);
    const xMeters = Math.max((maxLon - minLon) * 111320 * cosLat, 1);
    const yMeters = Math.max((maxLat - minLat) * 111320, 1);
    const scale = Math.min((W - 2 * PAD) / xMeters, (H - 2 * PAD) / yMeters);
    const offsetX = (W - (xMeters * scale)) / 2;
    const offsetY = (H - (yMeters * scale)) / 2;

    function project(lon, lat) {
        return {
            x: Math.round((offsetX + (lon - minLon) * 111320 * cosLat * scale) * 10) / 10,
            y: Math.round((offsetY + (maxLat - lat) * 111320 * scale) * 10) / 10
        };
    }

    const NS = 'http://www.w3.org/2000/svg';
    let svgParts = [
        `<svg xmlns="${NS}" width="700" height="350" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:350px;background:#f8fafc;">`,
        `<defs>
            <pattern id="rg" x="0" y="0" width="28" height="28" patternUnits="userSpaceOnUse">
                <path d="M 28 0 L 0 0 0 28" fill="none" stroke="#e2e8f0" stroke-width="0.5"/>
            </pattern>
        </defs>`,
        `<rect width="${W}" height="${H}" fill="url(#rg)"/>`
    ];

    // 1. Draw Field Boundary Polygon (behind)
    geojson.features.forEach(f => {
        if (f.properties.type !== 'field_boundary') return;
        const ring = f.geometry.coordinates[0];
        const pts = ring.map(c => { const pr = project(c[0], c[1]); return `${pr.x},${pr.y}`; }).join(' ');
        const p = f.properties;
        svgParts.push(
            `<polygon points="${pts}" fill="#fef08a" fill-opacity="0.1" stroke="#eab308" stroke-width="1" stroke-dasharray="4 2">
                <title>Field Survey Boundary | ${p.lidar_raw || 0} raw LiDAR → ${p.lidar_after_clip || 0} in boundary</title>
            </polygon>`
        );
    });

    // 2. Draw Match Lines
    geojson.features.forEach(f => {
        if (f.properties.type !== 'match_line') return;
        const p = f.properties;
        const color = p.score >= 0.7 ? '#10b981' : (p.score >= 0.5 ? '#f59e0b' : '#f43f5e');
        const [c0, c1] = f.geometry.coordinates;
        const a = project(c0[0], c0[1]);
        const b = project(c1[0], c1[1]);
        const dashArray = p.distance_m > 1.5 ? 'stroke-dasharray="3 2"' : '';
        svgParts.push(
            `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${color}" stroke-width="1.1" stroke-opacity="0.9" ${dashArray}>
                <title>Match: LiDAR #${p.lidar_id} ↔ Field #${p.field_id} | ${p.distance_m}m | Score: ${p.score}</title>
            </line>`
        );
    });

    // 3. Draw LiDAR Points (cyan)
    geojson.features.forEach(f => {
        if (f.properties.type !== 'lidar_point') return;
        const p = f.properties;
        const { x, y } = project(f.geometry.coordinates[0], f.geometry.coordinates[1]);
        svgParts.push(
            `<circle cx="${x}" cy="${y}" r="2.2" fill="#0284c7" stroke="#ffffff" stroke-width="0.6" fill-opacity="0.95">
                <title>LiDAR #${p.tree_id}: ${p.height_m || '?'}m, ${p.dbh_cm || '?'}cm DBH, Class ${p.height_class}</title>
            </circle>`
        );
    });

    // 4. Draw Field Points (orange)
    geojson.features.forEach(f => {
        if (f.properties.type !== 'field_point') return;
        const p = f.properties;
        const { x, y } = project(f.geometry.coordinates[0], f.geometry.coordinates[1]);
        svgParts.push(
            `<circle cx="${x}" cy="${y}" r="2.2" fill="#ea580c" stroke="#ffffff" stroke-width="0.6" fill-opacity="0.95">
                <title>Field #${p.field_id}: ${p.species || 'Tree'}, Class ${p.height_class}, ${p.dbh_cm || '?'}cm DBH</title>
            </circle>`
        );
    });

    // 5. Scale Bar & North Arrow
    const barMeters = 10;
    const barPx = Math.max(Math.round(barMeters * scale), 20);
    svgParts.push(
        `<g transform="translate(${W - barPx - 20}, ${H - 18})">
            <line x1="0" y1="0" x2="${barPx}" y2="0" stroke="#000000" stroke-width="2"/>
            <line x1="0" y1="-3" x2="0" y2="3" stroke="#000000" stroke-width="1.5"/>
            <line x1="${barPx}" y1="-3" x2="${barPx}" y2="3" stroke="#000000" stroke-width="1.5"/>
            <text x="${barPx/2}" y="-4" text-anchor="middle" fill="#000000" font-size="8.5" font-family="monospace" font-weight="700">${barMeters}m</text>
        </g>`,
        `<text x="${W - barPx - 34}" y="${H - 14}" fill="#000000" font-size="9" font-family="monospace" text-anchor="middle" font-weight="700">N↑</text>`
    );

    svgParts.push('</svg>');
    container.innerHTML = svgParts.join('\n');
}

// ---------------------------------------------------------------------------
// Print & PDF Export Triggers
// ---------------------------------------------------------------------------
function getActiveReportFilename() {
    let ds = currentResults;
    const select = document.getElementById('datasetSelect');
    const selectedId = select ? select.value : 'single';
    if (selectedId !== '__batch__' && currentResults && currentResults.datasets && currentResults.datasets[selectedId]) {
        ds = currentResults.datasets[selectedId];
    }
    const rawName = (ds && ds.filename) || document.getElementById('docActiveDatasetName')?.textContent?.trim() || 'TreeToolBox_Report';
    return rawName.replace(/\.[^/.]+$/, "");
}

async function printExecutiveReport() {
    generateExecutiveReport();
    
    let ds = currentResults;
    const select = document.getElementById('datasetSelect');
    const selectedId = select ? select.value : 'single';
    if (selectedId !== '__batch__' && currentResults && currentResults.datasets && currentResults.datasets[selectedId]) {
        ds = currentResults.datasets[selectedId];
    }
    if (ds && ds.geojson) {
        ensureReportMap(ds.geojson);
    }

    const cleanName = getActiveReportFilename();
    const origTitle = document.title;
    document.title = `${cleanName}_Executive_Report`;

    setTimeout(() => {
        window.print();
        setTimeout(() => { document.title = origTitle; }, 1000);
    }, 250);
}

async function saveExecutiveReportPdf() {
    generateExecutiveReport();

    let ds = currentResults;
    const select = document.getElementById('datasetSelect');
    const selectedId = select ? select.value : 'single';
    if (selectedId !== '__batch__' && currentResults && currentResults.datasets && currentResults.datasets[selectedId]) {
        ds = currentResults.datasets[selectedId];
    }
    if (ds && ds.geojson) {
        ensureReportMap(ds.geojson);
    }

    const cleanName = getActiveReportFilename();
    const pdfFilename = `${cleanName}_Executive_Report.pdf`;
    const wrapper = document.getElementById('printableAuditReport');

    if (wrapper) {
        wrapper.classList.add('is-exporting-pdf');
    }

    if (typeof html2pdf !== 'undefined' && wrapper) {
        const opt = {
            margin: 0,
            filename: pdfFilename,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, useCORS: true, logging: false, backgroundColor: '#ffffff' },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
            pagebreak: { mode: 'css' }
        };
        
        try {
            await html2pdf().set(opt).from(wrapper).save();
        } catch (err) {
            console.error('PDF export error:', err);
        } finally {
            if (wrapper) wrapper.classList.remove('is-exporting-pdf');
        }
    } else {
        // Fallback if offline/CDN unavailable: trigger print with pre-filled title
        const origTitle = document.title;
        document.title = `${cleanName}_Executive_Report`;
        window.print();
        setTimeout(() => {
            if (wrapper) wrapper.classList.remove('is-exporting-pdf');
            document.title = origTitle;
        }, 1000);
    }
}
