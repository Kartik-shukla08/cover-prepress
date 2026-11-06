/**
 * Markee Books Cover Studio — Author & Staff Friendly Interactive Cover Editor
 * Features:
 * - Pasteboard surround (560px around print template) with translucent grey overlay so parts/handles outside the template never disappear
 * - True Canva-style Crop Mode (stationary image with dimmed uncropped preview + draggable orange crop bars + pan-inside-crop)
 * - Interactive Spine Split Mode (draggable Left/Right spine cut lines on source spread)
 * - Grey loading overlay with spinner whenever book settings or cover splits are recalculated
 * - Clean, human-friendly labels and no preloaded sample cover by default
 */

const PASTEBOARD_PAD = 560; // Logical pixels of visible grey pasteboard margin around all 4 sides of the print template
const HANDLE_SIZE_SCREEN = 10;
let groupCounter = 1;

const state = {
  uploadMode: 'single', // 'single' | 'panels'
  viewMode: 'canvas',   // 'canvas' | 'divide' | 'proof'
  toolMode: 'select',   // 'select' | 'crop' | 'pan'

  singleFile: null,
  panelFiles: { back: null, spine: null, front: null },

  spec: null,
  guidelines: null,
  preflight: null,

  // Editable cover parts on the target canvas
  layers: [],
  selectedIds: [],

  // Active crop session when toolMode === 'crop'
  cropSession: null, // { layerId, origLayerState, fullX, fullY, fullW, fullH, scaleX, scaleY }

  // Source spread metadata for "Adjust Spine Split" mode
  sourceSpread: null, // { img, width, height, x_left, x_right, actual_crease_trim_px }

  proofImgSrc: null,

  // Viewport zoom & pan
  zoom: 0.22,
  zoomMode: 'fit', // 'fit' | 'custom'
  isSpaceDown: false,

  // Active mouse interaction state
  interaction: null,
  snapLines: [],

  // Undo / Redo stacks
  undoStack: [],
  redoStack: [],

  overlays: {
    bleed: true,
    trim: true,
    creases: true,
    spineSafe: true,
    coverSafe: true,
    barcode: true,
    measurements: true,
  },
};

document.addEventListener('DOMContentLoaded', () => {
  bindUIEvents();
  bindCanvasInteractions();
  // Load initial empty book template (no sample cover loaded by default)
  requestDecompose(false, 'Loading book template...');
});

/* ==========================================================================
   1. Loading Overlay Helpers
   ========================================================================== */

function showLoading(message = 'Updating book template & fitting cover...') {
  const overlay = document.getElementById('canvas-loading-overlay');
  const msgEl = document.getElementById('loading-message');
  if (msgEl) msgEl.textContent = message;
  if (overlay) overlay.classList.remove('hidden');
}

function hideLoading() {
  const overlay = document.getElementById('canvas-loading-overlay');
  if (overlay) overlay.classList.add('hidden');
}

/* ==========================================================================
   2. UI Event Bindings
   ========================================================================== */

function bindUIEvents() {
  const specSelectors = [
    'sel-publisher',
    'sel-binding',
    'sel-trim',
    'inp-pages',
    'inp-trim-w',
    'inp-trim-h',
    'sel-paper',
    'sel-ink',
    'sel-dpi',
  ];

  specSelectors.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => {
      if (id === 'sel-trim') {
        const isCustom = el.value === 'custom';
        document.getElementById('custom-trim-row').classList.toggle('hidden', !isCustom);
      }
      if (state.toolMode === 'crop') exitCropMode(true);
      requestDecompose(false, 'Resizing template & refitting cover parts...');
    });
  });

  // Upload mode tabs
  document.getElementById('tab-single-spread').addEventListener('click', () => {
    state.uploadMode = 'single';
    document.getElementById('tab-single-spread').classList.add('active');
    document.getElementById('tab-three-panels').classList.remove('active');
    document.getElementById('upload-single-container').classList.remove('hidden');
    document.getElementById('upload-panels-container').classList.add('hidden');
  });

  document.getElementById('tab-three-panels').addEventListener('click', () => {
    state.uploadMode = 'panels';
    document.getElementById('tab-three-panels').classList.add('active');
    document.getElementById('tab-single-spread').classList.remove('active');
    document.getElementById('upload-panels-container').classList.remove('hidden');
    document.getElementById('upload-single-container').classList.add('hidden');
  });

  // Single spread dropzone (sidebar + center stage drop support)
  const dzSingle = document.getElementById('dropzone-single');
  const fileSingle = document.getElementById('file-single');
  dzSingle.addEventListener('click', () => fileSingle.click());
  dzSingle.addEventListener('dragover', (e) => {
    e.preventDefault();
    dzSingle.classList.add('dragover');
  });
  dzSingle.addEventListener('dragleave', () => dzSingle.classList.remove('dragover'));
  dzSingle.addEventListener('drop', (e) => {
    e.preventDefault();
    dzSingle.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleSingleFileSelect(e.dataTransfer.files[0]);
    }
  });
  fileSingle.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleSingleFileSelect(e.target.files[0]);
    }
  });

  // Allow dropping a cover file directly onto the center canvas stage
  const stage = document.getElementById('canvas-stage');
  stage.addEventListener('dragover', (e) => e.preventDefault());
  stage.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleSingleFileSelect(e.dataTransfer.files[0]);
    }
  });

  // 3-panel dropzones
  ['back', 'spine', 'front'].forEach((panel) => {
    const dz = document.getElementById(`drop-${panel}`);
    const inp = document.getElementById(`file-${panel}`);
    dz.addEventListener('click', () => inp.click());
    inp.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        state.panelFiles[panel] = e.target.files[0];
        document.getElementById(`name-${panel}`).textContent = e.target.files[0].name;
        if (state.panelFiles.back && state.panelFiles.front) {
          requestDecompose(false, 'Combining Back, Spine & Front images...');
        }
      }
    });
  });

  // Adjust Spine Split & Auto-Fit buttons
  document.getElementById('btn-divide-source').addEventListener('click', () => {
    if (!state.sourceSpread) {
      alert('Please upload a full wrap cover image first so you can adjust its spine split.');
      return;
    }
    setViewMode('divide');
  });
  document.getElementById('btn-refresh-preview').addEventListener('click', () => {
    if (state.toolMode === 'crop') exitCropMode(true);
    requestDecompose(true, 'Auto-fitting cover parts to template...');
  });

  // Divide Mode banner buttons
  document.getElementById('btn-auto-detect').addEventListener('click', runCreaseAutoDetect);
  document.getElementById('btn-apply-source-cut').addEventListener('click', () => {
    if (state.sourceSpread) {
      document.getElementById('inp-spine-left').value = Math.round(state.sourceSpread.x_left);
      document.getElementById('inp-spine-right').value = Math.round(state.sourceSpread.x_right);
    }
    setViewMode('canvas');
    requestDecompose(false, 'Applying new spine split & rebuilding cover parts...');
  });

  // Crop Mode banner buttons
  const btnApplyCrop = document.getElementById('btn-apply-crop');
  if (btnApplyCrop) btnApplyCrop.addEventListener('click', () => exitCropMode(true));
  const btnCancelCrop = document.getElementById('btn-cancel-crop');
  if (btnCancelCrop) btnCancelCrop.addEventListener('click', () => exitCropMode(false));
  const btnUncropFull = document.getElementById('btn-uncrop-full');
  if (btnUncropFull) btnUncropFull.addEventListener('click', resetCropToFullImage);

  // Grouping & Collective Action buttons
  document.getElementById('btn-group-selected').addEventListener('click', groupSelectedLayers);
  document.getElementById('btn-ungroup-selected').addEventListener('click', ungroupSelectedLayers);
  document.getElementById('btn-select-spine-group').addEventListener('click', () => {
    if (state.toolMode === 'crop') exitCropMode(true);
    state.selectedIds = state.layers
      .filter((l) => l.kind.startsWith('spine_'))
      .map((l) => l.id);
    syncLayerListUI();
    renderCanvas();
  });
  document.getElementById('btn-select-all-panels').addEventListener('click', () => {
    if (state.toolMode === 'crop') exitCropMode(true);
    state.selectedIds = state.layers.map((l) => l.id);
    syncLayerListUI();
    renderCanvas();
  });
  document.getElementById('btn-snap-skeleton').addEventListener('click', snapPanelsToSkeleton);

  // Inspector numeric fields
  ['insp-x', 'insp-y', 'insp-w', 'insp-h'].forEach((id) => {
    document.getElementById(id).addEventListener('change', applyInspectorValues);
  });
  document.getElementById('chk-lock-aspect').addEventListener('change', (e) => {
    getSelectedLayers().forEach((l) => {
      l.lock_aspect = e.target.checked;
    });
    syncLayerListUI();
  });
  document.getElementById('btn-toggle-crop').addEventListener('click', () => {
    if (state.toolMode === 'crop') {
      exitCropMode(true);
    } else {
      enterCropMode();
    }
  });
  document.getElementById('btn-center-spine-opt').addEventListener('click', opticallyCenterSpineLayers);
  document.getElementById('btn-reset-layer').addEventListener('click', resetSelectedLayers);

  // View Mode Switcher
  document.getElementById('btn-view-canvas').addEventListener('click', () => setViewMode('canvas'));
  document.getElementById('btn-view-divide').addEventListener('click', () => {
    if (!state.sourceSpread) {
      alert('Upload a full wrap cover image first to adjust the spine split lines.');
      return;
    }
    setViewMode('divide');
  });
  document.getElementById('btn-view-proof').addEventListener('click', () => setViewMode('proof'));

  // Tool Mode Switcher
  document.getElementById('btn-tool-select').addEventListener('click', () => {
    if (state.toolMode === 'crop') exitCropMode(true);
    setToolMode('select');
  });
  document.getElementById('btn-tool-crop').addEventListener('click', () => {
    if (state.toolMode === 'crop') {
      exitCropMode(true);
    } else {
      enterCropMode();
    }
  });
  document.getElementById('btn-tool-pan').addEventListener('click', () => {
    if (state.toolMode === 'crop') exitCropMode(true);
    setToolMode('pan');
  });
  document.getElementById('btn-undo').addEventListener('click', undoAction);
  document.getElementById('btn-redo').addEventListener('click', redoAction);

  // Zoom Controls (1.10x = 10% per click — half of 20%)
  const ZOOM_STEP = 1.10;
  document.getElementById('btn-zoom-in').addEventListener('click', () => {
    const base = state.targetZoom || state.zoom;
    setZoom(base * ZOOM_STEP);
  });
  document.getElementById('btn-zoom-out').addEventListener('click', () => {
    const base = state.targetZoom || state.zoom;
    setZoom(base / ZOOM_STEP);
  });
  document.getElementById('btn-zoom-reset').addEventListener('click', () => fitCanvasToViewport(true));
  document.getElementById('btn-zoom-100').addEventListener('click', () => setZoom(1.0));
  document.getElementById('btn-zoom-spine').addEventListener('click', zoomToSpineSafeZone);

  // Guideline Checkboxes
  const checkboxMap = {
    'chk-bleed': 'bleed',
    'chk-trim': 'trim',
    'chk-creases': 'creases',
    'chk-spine-safe': 'spineSafe',
    'chk-cover-safe': 'coverSafe',
    'chk-barcode': 'barcode',
    'chk-measurements': 'measurements',
  };
  Object.entries(checkboxMap).forEach(([chkId, key]) => {
    const el = document.getElementById(chkId);
    if (!el) return;
    el.addEventListener('change', (e) => {
      state.overlays[key] = e.target.checked;
      renderCanvas();
    });
  });

  // Header Popover Menus (Guides & More Export Formats)
  const guidesBtn = document.getElementById('btn-guides-menu');
  const guidesPopover = document.getElementById('guides-popover');
  const moreExportsBtn = document.getElementById('btn-more-exports');
  const exportPopover = document.getElementById('export-popover');

  const closeAllPopovers = () => {
    if (guidesPopover) guidesPopover.classList.add('hidden');
    if (exportPopover) exportPopover.classList.add('hidden');
  };

  if (guidesBtn && guidesPopover) {
    guidesBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const wasHidden = guidesPopover.classList.contains('hidden');
      closeAllPopovers();
      if (wasHidden) guidesPopover.classList.remove('hidden');
    });
    guidesPopover.addEventListener('click', (e) => e.stopPropagation());
  }

  if (moreExportsBtn && exportPopover) {
    moreExportsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const wasHidden = exportPopover.classList.contains('hidden');
      closeAllPopovers();
      if (wasHidden) exportPopover.classList.remove('hidden');
    });
    exportPopover.addEventListener('click', (e) => e.stopPropagation());
  }

  document.addEventListener('click', () => closeAllPopovers());

  // Export buttons
  document.getElementById('btn-export-pdf').addEventListener('click', () => {
    closeAllPopovers();
    triggerExport('pdf');
  });
  document.getElementById('btn-export-png').addEventListener('click', () => {
    closeAllPopovers();
    triggerExport('png');
  });
  document.getElementById('btn-export-jpg').addEventListener('click', () => {
    closeAllPopovers();
    triggerExport('jpg');
  });
  document.getElementById('btn-export-zip').addEventListener('click', () => {
    closeAllPopovers();
    triggerExport('zip');
  });

  // Collapsible Print Check Drawer toggle
  const toggleDrawer = () => {
    closeAllPopovers();
    const ws = document.getElementById('studio-workspace');
    const dr = document.getElementById('sidebar-right');
    const btn = document.getElementById('btn-toggle-specs-drawer');
    if (!ws || !dr) return;
    const isHidden = dr.classList.toggle('hidden');
    ws.classList.toggle('drawer-collapsed', isHidden);
    if (btn) btn.textContent = isHidden ? '📊 View Print Measurements' : '📊 Hide Print Measurements';
    if (state.zoomMode === 'fit') {
      requestAnimationFrame(() => fitCanvasToViewport());
    }
  };
  const btnDrawer = document.getElementById('btn-toggle-specs-drawer');
  if (btnDrawer) btnDrawer.addEventListener('click', toggleDrawer);
  const btnCloseDrawer = document.getElementById('btn-close-specs-drawer');
  if (btnCloseDrawer) btnCloseDrawer.addEventListener('click', toggleDrawer);

  window.addEventListener('resize', () => {
    if (state.zoomMode === 'fit') {
      fitCanvasToViewport();
    }
  });
}

function handleSingleFileSelect(file) {
  state.singleFile = file;
  document.getElementById('file-single-name').textContent = file.name;
  document.getElementById('inp-spine-left').value = '';
  document.getElementById('inp-spine-right').value = '';
  if (state.toolMode === 'crop') exitCropMode(false);
  requestDecompose(true, 'Splitting cover into Back, Spine & Front parts...');
}

/* ==========================================================================
   3. Backend API Calls (/api/decompose, /api/crease-detect, /api/export)
   ========================================================================== */

function buildFormData(resetCutOverrides = false) {
  const fd = new FormData();
  fd.append('publisher', document.getElementById('sel-publisher').value);
  fd.append('binding', document.getElementById('sel-binding').value);

  const trimVal = document.getElementById('sel-trim').value;
  if (trimVal === 'custom') {
    fd.append('trim_w_in', document.getElementById('inp-trim-w').value);
    fd.append('trim_h_in', document.getElementById('inp-trim-h').value);
  } else {
    fd.append('trim_size', trimVal);
  }

  fd.append('page_count', document.getElementById('inp-pages').value);
  fd.append('paper_type', document.getElementById('sel-paper').value);
  fd.append('ink_type', document.getElementById('sel-ink').value);
  fd.append('dpi', document.getElementById('sel-dpi').value);

  if (!resetCutOverrides) {
    const spLeft = document.getElementById('inp-spine-left').value;
    const spRight = document.getElementById('inp-spine-right').value;
    if (spLeft !== '' && spRight !== '') {
      fd.append('spine_bounds', `${spLeft},${spRight}`);
    }
  }

  if (state.uploadMode === 'single') {
    if (state.singleFile) {
      fd.append('file', state.singleFile);
    }
  } else {
    if (state.panelFiles.back) fd.append('file_back', state.panelFiles.back);
    if (state.panelFiles.spine) fd.append('file_spine', state.panelFiles.spine);
    if (state.panelFiles.front) fd.append('file_front', state.panelFiles.front);
  }

  return fd;
}

async function requestDecompose(resetCutOverrides = false, loadingMsg = 'Updating book template & fitting cover...') {
  const badge = document.getElementById('status-badge');
  badge.textContent = 'WORKING...';
  badge.className = 'badge badge-ready';
  showLoading(loadingMsg);

  if (resetCutOverrides) {
    document.getElementById('inp-spine-left').value = '';
    document.getElementById('inp-spine-right').value = '';
  }

  try {
    const fd = buildFormData(resetCutOverrides);
    const resp = await fetch('/api/decompose', {
      method: 'POST',
      body: fd,
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || 'Failed to update cover');
    }
    const data = await resp.json();
    state.spec = data.spec;
    state.guidelines = data.guidelines;
    state.preflight = data.preflight;
    state.proofImgSrc = data.proof_image_base64 || null;

    if (state.proofImgSrc) {
      document.getElementById('proof-image-view').src = state.proofImgSrc;
    }

    if (data.source_spread && data.source_spread.image_base64) {
      const srcImg = await loadImageAsync(data.source_spread.image_base64);
      state.sourceSpread = {
        img: srcImg,
        width: data.source_spread.width,
        height: data.source_spread.height,
        x_left: data.source_spread.x_left,
        x_right: data.source_spread.x_right,
        actual_crease_trim_px: data.source_spread.actual_crease_trim_px || 0,
      };
    } else {
      state.sourceSpread = null;
    }

    const loadedLayers = [];
    for (const lyrData of data.layers || []) {
      const imgObj = await loadImageAsync(lyrData.image_base64);
      loadedLayers.push({
        ...lyrData,
        img: imgObj,
        natW: imgObj.naturalWidth || imgObj.width,
        natH: imgObj.naturalHeight || imgObj.height,
        crop: lyrData.crop || { top: 0, right: 0, bottom: 0, left: 0 },
      });
    }
    state.layers = loadedLayers;
    state.undoStack = [];
    state.redoStack = [];

    const spineIds = state.layers.filter((l) => l.group_id === 'spine_group').map((l) => l.id);
    state.selectedIds = spineIds.length > 0 ? spineIds : state.layers.slice(0, 1).map((l) => l.id);

    updateSidebarMetrics();
    syncLayerListUI();
    fitCanvasToViewport();
    renderCanvas();
  } catch (err) {
    console.error('Decompose error:', err);
    badge.textContent = 'ERROR';
    badge.className = 'badge badge-fail';
  } finally {
    hideLoading();
  }
}

function loadImageAsync(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e);
    img.src = src;
  });
}

async function runCreaseAutoDetect() {
  if (!state.singleFile && !state.sourceSpread) return;
  showLoading('Auto-detecting spine fold lines...');

  try {
    let resp;
    if (state.singleFile) {
      const fd = new FormData();
      fd.append('file', state.singleFile);
      resp = await fetch('/api/crease-detect', { method: 'POST', body: fd });
    } else if (state.sourceSpread && state.sourceSpread.img) {
      resp = await fetch('/api/crease-detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_base64: state.sourceSpread.img.src }),
      });
    }
    if (resp && resp.ok) {
      const data = await resp.json();
      if (state.sourceSpread) {
        state.sourceSpread.x_left = data.x_left;
        state.sourceSpread.x_right = data.x_right;
      }
      document.getElementById('inp-spine-left').value = data.x_left;
      document.getElementById('inp-spine-right').value = data.x_right;
      renderCanvas();
    }
  } catch (err) {
    console.error('Auto-detect error:', err);
  } finally {
    hideLoading();
  }
}

/* ==========================================================================
   4. Viewport Zoom, Pasteboard Dimensions & Scroll Management
   ========================================================================== */

function getActiveCanvasPhysicalSize() {
  if (state.viewMode === 'divide' && state.sourceSpread) {
    return {
      physW: state.sourceSpread.width,
      physH: state.sourceSpread.height,
      pad: 0,
      templateW: state.sourceSpread.width,
      templateH: state.sourceSpread.height,
    };
  }
  const tw = state.guidelines ? state.guidelines.width_px : 3776;
  const th = state.guidelines ? state.guidelines.height_px : 2775;
  return {
    physW: tw + PASTEBOARD_PAD * 2,
    physH: th + PASTEBOARD_PAD * 2,
    pad: PASTEBOARD_PAD,
    templateW: tw,
    templateH: th,
  };
}

function fitCanvasToViewport(smooth = false) {
  const stage = document.getElementById('canvas-stage');
  if (!stage) return;
  const { physW, physH, templateW, templateH } = getActiveCanvasPhysicalSize();
  const availW = Math.max(320, stage.clientWidth - 48);
  const availH = Math.max(240, stage.clientHeight - 48);
  // Fit so the entire template + a comfortable slice of the grey pasteboard is visible
  const targetW = state.viewMode === 'divide' ? physW : templateW + PASTEBOARD_PAD * 0.9;
  const targetH = state.viewMode === 'divide' ? physH : templateH + PASTEBOARD_PAD * 0.9;
  const fitZoom = Math.min(availW / targetW, availH / targetH);
  state.zoomMode = 'fit';
  if (smooth) {
    animateZoomTo(fitZoom, true);
  } else {
    if (state.zoomAnimFrame) {
      cancelAnimationFrame(state.zoomAnimFrame);
      state.zoomAnimFrame = null;
    }
    state.targetZoom = Math.max(0.06, Math.min(4.0, fitZoom));
    applyZoomValue(state.targetZoom, true);
  }
}

function setZoom(newZoom, smooth = true) {
  state.zoomMode = 'custom';
  if (smooth) {
    animateZoomTo(newZoom, false);
  } else {
    if (state.zoomAnimFrame) {
      cancelAnimationFrame(state.zoomAnimFrame);
      state.zoomAnimFrame = null;
    }
    state.targetZoom = Math.max(0.06, Math.min(4.0, newZoom));
    applyZoomValue(state.targetZoom, false);
  }
}

function animateZoomTo(targetZ, isFit = false, customCenterRatio = null) {
  const clamped = Math.max(0.06, Math.min(4.0, targetZ));
  state.targetZoom = clamped;
  state.targetZoomIsFit = isFit;
  if (customCenterRatio) {
    state.zoomCenterRatio = customCenterRatio;
  }
  if (state.zoomAnimFrame) return;

  const stepZoom = () => {
    const diff = state.targetZoom - state.zoom;
    if (Math.abs(diff) < 0.004) {
      state.zoomAnimFrame = null;
      applyZoomValue(state.targetZoom, state.targetZoomIsFit, state.zoomCenterRatio, true);
      state.zoomCenterRatio = null;
      return;
    }
    // Fast 3-frame GPU CSS scale without expensive intermediate canvas redraws
    const nextZ = state.zoom + diff * 0.55;
    applyZoomValue(nextZ, state.targetZoomIsFit, state.zoomCenterRatio, false);
    state.zoomAnimFrame = requestAnimationFrame(stepZoom);
  };
  state.zoomAnimFrame = requestAnimationFrame(stepZoom);
}

function applyZoomValue(z, isFit = false, customCenterRatio = null, redrawCanvas = true) {
  const stage = document.getElementById('canvas-stage');
  const canvas = document.getElementById('studio-canvas');
  const { physW, physH } = getActiveCanvasPhysicalSize();

  const prevScrollRatioX = customCenterRatio
    ? customCenterRatio.x
    : stage.scrollWidth > 0
    ? (stage.scrollLeft + stage.clientWidth / 2) / stage.scrollWidth
    : 0.5;
  const prevScrollRatioY = customCenterRatio
    ? customCenterRatio.y
    : stage.scrollHeight > 0
    ? (stage.scrollTop + stage.clientHeight / 2) / stage.scrollHeight
    : 0.5;

  state.zoom = Math.max(0.06, Math.min(4.0, z));

  const displayW = Math.round(physW * state.zoom);
  const displayH = Math.round(physH * state.zoom);
  canvas.style.width = `${displayW}px`;
  canvas.style.height = `${displayH}px`;

  const pct = Math.round(state.zoom * 100);
  document.getElementById('zoom-label').textContent = isFit ? `Fit (${pct}%)` : `${pct}%`;

  if (redrawCanvas) {
    renderCanvas();
  }

  // Synchronously anchor scroll position so zooming is rock-solid with zero frame jitter
  if (isFit) {
    stage.scrollLeft = Math.max(0, (stage.scrollWidth - stage.clientWidth) / 2);
    stage.scrollTop = Math.max(0, (stage.scrollHeight - stage.clientHeight) / 2);
  } else if (stage.scrollWidth > stage.clientWidth || stage.scrollHeight > stage.clientHeight) {
    stage.scrollLeft = Math.max(0, prevScrollRatioX * stage.scrollWidth - stage.clientWidth / 2);
    stage.scrollTop = Math.max(0, prevScrollRatioY * stage.scrollHeight - stage.clientHeight / 2);
  }
}

function zoomToSpineSafeZone() {
  if (state.viewMode !== 'canvas') {
    setViewMode('canvas');
  }
  state.zoomMode = 'custom';
  animateZoomTo(1.15, false, { x: 0.5, y: 0.44 });
}

function syncContextBarVisibility() {
  const normalBar = document.getElementById('context-normal-bar');
  const cropBar = document.getElementById('crop-mode-banner');
  const divideBar = document.getElementById('divide-mode-banner');

  const isDivide = state.viewMode === 'divide';
  const isProof = state.viewMode === 'proof';
  const isCrop = state.viewMode === 'canvas' && state.toolMode === 'crop';
  const isNormal = state.viewMode === 'canvas' && state.toolMode !== 'crop';

  if (normalBar) normalBar.classList.toggle('hidden', !isNormal || isProof);
  if (cropBar) cropBar.classList.toggle('hidden', !isCrop || isProof);
  if (divideBar) divideBar.classList.toggle('hidden', !isDivide || isProof);
}

function setViewMode(mode) {
  if (state.toolMode === 'crop' && mode !== 'canvas') {
    exitCropMode(true);
  }
  state.viewMode = mode;
  document.getElementById('btn-view-canvas').classList.toggle('active', mode === 'canvas');
  document.getElementById('btn-view-divide').classList.toggle('active', mode === 'divide');
  document.getElementById('btn-view-proof').classList.toggle('active', mode === 'proof');

  const sizer = document.getElementById('canvas-scroll-sizer');
  const proofImg = document.getElementById('proof-image-view');

  syncContextBarVisibility();

  if (mode === 'proof') {
    sizer.classList.add('hidden');
    proofImg.classList.remove('hidden');
  } else {
    sizer.classList.remove('hidden');
    proofImg.classList.add('hidden');
    fitCanvasToViewport();
    renderCanvas();
  }
}

function setToolMode(mode) {
  state.toolMode = mode;
  document.getElementById('btn-tool-select').classList.toggle('active', mode === 'select');
  document.getElementById('btn-tool-crop').classList.toggle('active', mode === 'crop');
  document.getElementById('btn-tool-pan').classList.toggle('active', mode === 'pan');

  syncContextBarVisibility();

  const cropBtn = document.getElementById('btn-toggle-crop');
  if (cropBtn) {
    cropBtn.textContent = mode === 'crop' ? '✅ Done Cropping' : '✂️ Crop This Part';
  }
  renderCanvas();
}

/* ==========================================================================
   5. True Canva-Style Crop Mode (Stationary Image + Orange Crop Window)
   ========================================================================== */

function computeLayerFullUncroppedBox(lyr) {
  const c = lyr.crop || { top: 0, right: 0, bottom: 0, left: 0 };
  const visSrcW = Math.max(1, lyr.natW - c.left - c.right);
  const visSrcH = Math.max(1, lyr.natH - c.top - c.bottom);
  const scaleX = lyr.w / visSrcW;
  const scaleY = lyr.h / visSrcH;
  return {
    fullX: lyr.x - c.left * scaleX,
    fullY: lyr.y - c.top * scaleY,
    fullW: lyr.natW * scaleX,
    fullH: lyr.natH * scaleY,
    scaleX,
    scaleY,
  };
}

function enterCropMode(targetLayer = null) {
  if (state.viewMode !== 'canvas') setViewMode('canvas');
  let lyr = targetLayer;
  if (!lyr) {
    const sel = getSelectedLayers();
    if (sel.length === 0) {
      alert('Click a cover part (such as Back Cover, Front Cover, or Spine) first, then click Crop.');
      return;
    }
    // Prefer cropping a panel if multiple layers are selected
    lyr = sel.find((l) => l.kind === 'panel') || sel[sel.length - 1];
  }

  state.selectedIds = [lyr.id];
  const fb = computeLayerFullUncroppedBox(lyr);
  state.cropSession = {
    layerId: lyr.id,
    origState: {
      x: lyr.x,
      y: lyr.y,
      w: lyr.w,
      h: lyr.h,
      crop: { ...lyr.crop },
    },
    ...fb,
  };
  pushUndoSnapshot();
  syncLayerListUI();
  setToolMode('crop');
}

function exitCropMode(commit = true) {
  if (state.cropSession && !commit) {
    const lyr = state.layers.find((l) => l.id === state.cropSession.layerId);
    if (lyr) {
      const os = state.cropSession.origState;
      lyr.x = os.x;
      lyr.y = os.y;
      lyr.w = os.w;
      lyr.h = os.h;
      lyr.crop = { ...os.crop };
    }
    state.undoStack.pop();
  }
  state.cropSession = null;
  setToolMode('select');
  syncLayerListUI();
  updateLiveSpineTelemetry();
  renderCanvas();
}

function resetCropToFullImage() {
  if (!state.cropSession) return;
  const lyr = state.layers.find((l) => l.id === state.cropSession.layerId);
  if (!lyr) return;
  lyr.x = state.cropSession.fullX;
  lyr.y = state.cropSession.fullY;
  lyr.w = state.cropSession.fullW;
  lyr.h = state.cropSession.fullH;
  lyr.crop = { top: 0, right: 0, bottom: 0, left: 0 };
  syncLayerListUI();
  renderCanvas();
}

/* ==========================================================================
   6. Layer Selection, Grouping, Undo/Redo & Smart Actions
   ========================================================================== */

function pushUndoSnapshot() {
  const snap = state.layers.map((l) => ({
    id: l.id,
    x: l.x,
    y: l.y,
    w: l.w,
    h: l.h,
    group_id: l.group_id,
    lock_aspect: l.lock_aspect,
    visible: l.visible,
    crop: { ...l.crop },
  }));
  state.undoStack.push(snap);
  if (state.undoStack.length > 40) state.undoStack.shift();
  state.redoStack = [];
}

function applySnapshot(snap) {
  snap.forEach((s) => {
    const lyr = state.layers.find((l) => l.id === s.id);
    if (lyr) {
      lyr.x = s.x;
      lyr.y = s.y;
      lyr.w = s.w;
      lyr.h = s.h;
      lyr.group_id = s.group_id;
      lyr.lock_aspect = s.lock_aspect;
      lyr.visible = s.visible;
      lyr.crop = { ...s.crop };
    }
  });
  syncLayerListUI();
  updateLiveSpineTelemetry();
  renderCanvas();
}

function undoAction() {
  if (state.toolMode === 'crop') exitCropMode(false);
  if (state.undoStack.length === 0) return;
  const current = state.layers.map((l) => ({
    id: l.id,
    x: l.x,
    y: l.y,
    w: l.w,
    h: l.h,
    group_id: l.group_id,
    lock_aspect: l.lock_aspect,
    visible: l.visible,
    crop: { ...l.crop },
  }));
  state.redoStack.push(current);
  const prev = state.undoStack.pop();
  applySnapshot(prev);
}

function redoAction() {
  if (state.redoStack.length === 0) return;
  const current = state.layers.map((l) => ({
    id: l.id,
    x: l.x,
    y: l.y,
    w: l.w,
    h: l.h,
    group_id: l.group_id,
    lock_aspect: l.lock_aspect,
    visible: l.visible,
    crop: { ...l.crop },
  }));
  state.undoStack.push(current);
  const next = state.redoStack.pop();
  applySnapshot(next);
}

function getSelectedLayers() {
  return state.layers.filter((l) => state.selectedIds.includes(l.id) && l.visible);
}

function getSelectionBoundingBox(layers = getSelectedLayers()) {
  if (!layers || layers.length === 0) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  layers.forEach((l) => {
    minX = Math.min(minX, l.x);
    minY = Math.min(minY, l.y);
    maxX = Math.max(maxX, l.x + l.w);
    maxY = Math.max(maxY, l.y + l.h);
  });
  return { x: minX, y: minY, w: Math.max(1, maxX - minX), h: Math.max(1, maxY - minY) };
}

function groupSelectedLayers() {
  const sel = getSelectedLayers();
  if (sel.length < 2) return;
  pushUndoSnapshot();
  const newGroupId = `custom_group_${groupCounter++}`;
  sel.forEach((l) => {
    l.group_id = newGroupId;
  });
  syncLayerListUI();
  renderCanvas();
}

function ungroupSelectedLayers() {
  const sel = getSelectedLayers();
  if (sel.length === 0) return;
  pushUndoSnapshot();
  sel.forEach((l) => {
    l.group_id = null;
  });
  state.selectedIds = [sel[sel.length - 1].id];
  syncLayerListUI();
  renderCanvas();
}

function snapPanelsToSkeleton() {
  if (!state.guidelines) return;
  if (state.toolMode === 'crop') exitCropMode(true);
  pushUndoSnapshot();
  const W = state.guidelines.width_px;
  const H = state.guidelines.height_px;
  const xFL = state.guidelines.spine_creases.calculated_x_left;
  const xFR = state.guidelines.spine_creases.calculated_x_right;

  state.layers.forEach((l) => {
    if (l.id === 'back_panel') {
      l.x = 0;
      l.y = 0;
      l.w = xFL;
      l.h = H;
    } else if (l.id === 'spine_bg') {
      l.x = xFL;
      l.y = 0;
      l.w = xFR - xFL;
      l.h = H;
    } else if (l.id === 'front_panel') {
      l.x = xFR;
      l.y = 0;
      l.w = W - xFR;
      l.h = H;
    }
  });
  syncLayerListUI();
  renderCanvas();
}

function opticallyCenterSpineLayers() {
  if (!state.guidelines) return;
  pushUndoSnapshot();
  const xFL = state.guidelines.spine_creases.calculated_x_left;
  const xFR = state.guidelines.spine_creases.calculated_x_right;
  const spineCenter = (xFL + xFR) / 2.0;

  state.layers.forEach((l) => {
    if (l.kind === 'spine_text' || l.kind === 'spine_ornament') {
      const glyphCenterRatio = (l.glyph_left_ratio + l.glyph_right_ratio) / 2.0;
      const bias = l.kind === 'spine_text' ? -1.0 : 0.0;
      l.x = Math.round(spineCenter - l.w * glyphCenterRatio + bias);
    }
  });
  syncLayerListUI();
  updateLiveSpineTelemetry();
  renderCanvas();
}

function resetSelectedLayers() {
  if (state.toolMode === 'crop') exitCropMode(false);
  const sel = getSelectedLayers();
  if (sel.length === 0) return;
  pushUndoSnapshot();
  sel.forEach((l) => {
    l.x = l.orig_x;
    l.y = l.orig_y;
    l.w = l.orig_w;
    l.h = l.orig_h;
    l.crop = { top: 0, right: 0, bottom: 0, left: 0 };
  });
  syncLayerListUI();
  updateLiveSpineTelemetry();
  renderCanvas();
}

function applyInspectorValues() {
  const sel = getSelectedLayers();
  if (sel.length === 0) return;
  pushUndoSnapshot();
  const bbox = getSelectionBoundingBox(sel);
  const newX = parseFloat(document.getElementById('insp-x').value) || bbox.x;
  const newY = parseFloat(document.getElementById('insp-y').value) || bbox.y;
  const newW = Math.max(4, parseFloat(document.getElementById('insp-w').value) || bbox.w);
  const newH = Math.max(4, parseFloat(document.getElementById('insp-h').value) || bbox.h);

  const scaleX = newW / bbox.w;
  const scaleY = newH / bbox.h;

  sel.forEach((l) => {
    l.x = newX + (l.x - bbox.x) * scaleX;
    l.y = newY + (l.y - bbox.y) * scaleY;
    l.w = Math.max(4, l.w * scaleX);
    l.h = Math.max(4, l.h * scaleY);
  });
  syncLayerListUI();
  updateLiveSpineTelemetry();
  renderCanvas();
}

function syncLayerListUI() {
  const listEl = document.getElementById('layer-list');
  if (!listEl) return;

  if (state.layers.length === 0) {
    listEl.innerHTML =
      '<div class="empty-layers-msg">Upload a cover image above to split and edit Back Cover, Spine, and Front Cover parts.</div>';
    document.getElementById('inspector-box').classList.add('hidden');
    document.getElementById('selection-status').textContent = 'No cover image loaded yet';
    return;
  }

  listEl.innerHTML = '';
  [...state.layers].reverse().forEach((lyr) => {
    const isSel = state.selectedIds.includes(lyr.id);
    const row = document.createElement('div');
    row.className = `layer-item${isSel ? ' selected' : ''}`;

    const left = document.createElement('div');
    left.className = 'layer-left';

    const visBtn = document.createElement('button');
    visBtn.className = 'layer-vis-btn';
    visBtn.textContent = lyr.visible ? '👁️' : '🚫';
    visBtn.title = 'Show / Hide Part';
    visBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      lyr.visible = !lyr.visible;
      syncLayerListUI();
      renderCanvas();
    });

    const nameSpan = document.createElement('span');
    nameSpan.className = 'layer-name';
    nameSpan.textContent = lyr.name;

    left.appendChild(visBtn);
    left.appendChild(nameSpan);

    const badges = document.createElement('div');
    badges.className = 'layer-badges';
    const hasCrop =
      lyr.crop && (lyr.crop.left > 1 || lyr.crop.right > 1 || lyr.crop.top > 1 || lyr.crop.bottom > 1);
    if (hasCrop) {
      const cp = document.createElement('span');
      cp.className = 'lock-pill';
      cp.textContent = 'Cropped';
      badges.appendChild(cp);
    }
    if (lyr.group_id) {
      const gp = document.createElement('span');
      gp.className = 'group-pill';
      gp.textContent = lyr.group_id === 'spine_group' ? 'Spine Group' : 'Grouped';
      badges.appendChild(gp);
    }

    row.appendChild(left);
    row.appendChild(badges);

    row.addEventListener('click', (e) => {
      if (state.toolMode === 'crop' && state.cropSession && state.cropSession.layerId !== lyr.id) {
        exitCropMode(true);
      }
      if (e.shiftKey) {
        if (state.selectedIds.includes(lyr.id)) {
          state.selectedIds = state.selectedIds.filter((id) => id !== lyr.id);
        } else {
          state.selectedIds.push(lyr.id);
        }
      } else {
        state.selectedIds = [lyr.id];
      }
      syncLayerListUI();
      renderCanvas();
    });

    row.addEventListener('dblclick', () => {
      enterCropMode(lyr);
    });

    listEl.appendChild(row);
  });

  const sel = getSelectedLayers();
  const inspBox = document.getElementById('inspector-box');
  const footerSel = document.getElementById('selection-status');

  if (sel.length === 0) {
    inspBox.classList.add('hidden');
    footerSel.textContent = 'Click any cover part to Move, Resize, or Crop';
  } else {
    inspBox.classList.remove('hidden');
    const bbox = getSelectionBoundingBox(sel);
    document.getElementById('inspector-layer-name').textContent =
      sel.length === 1 ? sel[0].name : `${sel.length} Parts Selected`;
    document.getElementById('chk-lock-aspect').checked = sel.every((l) => l.lock_aspect);
    document.getElementById('insp-x').value = Math.round(bbox.x);
    document.getElementById('insp-y').value = Math.round(bbox.y);
    document.getElementById('insp-w').value = Math.round(bbox.w);
    document.getElementById('insp-h').value = Math.round(bbox.h);
    footerSel.textContent =
      state.toolMode === 'crop'
        ? `✂️ Cropping: ${sel[0].name} (Press Enter when done)`
        : sel.length === 1
        ? `Selected: ${sel[0].name} (${Math.round(bbox.w)} × ${Math.round(bbox.h)} px)`
        : `Selected: ${sel.length} Parts (${Math.round(bbox.w)} × ${Math.round(bbox.h)} px)`;
  }
}

/* ==========================================================================
   7. Interactive Canvas Mouse / Pointer / Double-Click / Keyboard Engine
   ========================================================================== */

function getCanvasCoords(e) {
  const canvas = document.getElementById('studio-canvas');
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / Math.max(1, rect.width);
  const scaleY = canvas.height / Math.max(1, rect.height);
  const { pad } = getActiveCanvasPhysicalSize();
  return {
    x: (e.clientX - rect.left) * scaleX - pad,
    y: (e.clientY - rect.top) * scaleY - pad,
  };
}

function getHandleRadiusCanvas(bbox) {
  const zoomSafe = Math.max(0.06, state.zoom);
  // Small, unobtrusive screen radius when zoomed out (~3.2px), scaling gently up to 5.5px when zoomed in
  const rScreen = Math.min(5.5, Math.max(3.0, 2.4 + state.zoom * 3.2));
  let rCanvas = rScreen / zoomSafe;
  if (bbox) {
    const minDim = Math.max(8, Math.min(bbox.w, bbox.h));
    // Clamp so handles on narrow parts (like the spine when zoomed out) never overlap each other
    rCanvas = Math.min(rCanvas, Math.max(1.8 / zoomSafe, minDim * 0.16));
  }
  return rCanvas;
}

function getHandlePositions(bbox) {
  const { x, y, w, h } = bbox;
  return {
    nw: { x: x, y: y, cursor: 'nwse-resize' },
    n: { x: x + w / 2, y: y, cursor: 'ns-resize' },
    ne: { x: x + w, y: y, cursor: 'nesw-resize' },
    e: { x: x + w, y: y + h / 2, cursor: 'ew-resize' },
    se: { x: x + w, y: y + h, cursor: 'nwse-resize' },
    s: { x: x + w / 2, y: y + h, cursor: 'ns-resize' },
    sw: { x: x, y: y + h, cursor: 'nesw-resize' },
    w: { x: x, y: y + h / 2, cursor: 'ew-resize' },
  };
}

function hitTestHandles(pt, bbox) {
  if (!bbox) return null;
  const zoomSafe = Math.max(0.06, state.zoom);
  const r = getHandleRadiusCanvas(bbox);
  const padHit = 3.5 / zoomSafe;
  const maxHitDist = Math.min(r + padHit, Math.max(bbox.w, bbox.h, 16) * 0.45);
  const handles = getHandlePositions(bbox);
  let bestName = null;
  let bestDist = Infinity;
  for (const [name, hPt] of Object.entries(handles)) {
    const d = Math.hypot(pt.x - hPt.x, pt.y - hPt.y);
    if (d <= maxHitDist && d < bestDist) {
      bestDist = d;
      bestName = name;
    }
  }
  return bestName;
}

function getSkeletalSnapTargets() {
  if (!state.guidelines) return { vTargets: [], hTargets: [] };
  const g = state.guidelines;
  const W = g.width_px;
  const H = g.height_px;
  const [bx0, by0, bx1, by1] = g.bleed_box || [0, 0, W, H];
  const [tx0, ty0, tx1, ty1] = g.trim_box || [0, 0, W, H];
  const xFL = g.spine_creases.calculated_x_left;
  const xFR = g.spine_creases.calculated_x_right;
  const [sx0, sy0, sx1, sy1] = g.spine_safe_zone || [xFL, ty0, xFR, ty1];
  const [bsx0, bsy0, bsx1, bsy1] = g.back_cover_safe_zone || [tx0, ty0, xFL, ty1];
  const [fsx0, fsy0, fsx1, fsy1] = g.front_cover_safe_zone || [xFR, ty0, tx1, ty1];

  const vTargets = [
    { pos: bx0, label: 'Left Bleed' },
    { pos: tx0, label: 'Left Book Edge' },
    { pos: bsx0, label: 'Back Safe Left' },
    { pos: (tx0 + xFL) / 2.0, label: 'Back Center' },
    { pos: bsx1, label: 'Back Safe Right' },
    { pos: xFL, label: 'Left Spine Fold' },
    { pos: sx0, label: 'Spine Safe Left' },
    { pos: (xFL + xFR) / 2.0, label: 'Spine Center' },
    { pos: sx1, label: 'Spine Safe Right' },
    { pos: xFR, label: 'Right Spine Fold' },
    { pos: fsx0, label: 'Front Safe Left' },
    { pos: (xFR + tx1) / 2.0, label: 'Front Center' },
    { pos: fsx1, label: 'Front Safe Right' },
    { pos: tx1, label: 'Right Book Edge' },
    { pos: bx1, label: 'Right Bleed' },
  ];

  const hTargets = [
    { pos: by0, label: 'Top Bleed' },
    { pos: ty0, label: 'Top Book Edge' },
    { pos: bsy0, label: 'Top Safe Margin' },
    { pos: sy0, label: 'Top Spine Safe' },
    { pos: H / 2.0, label: 'Middle' },
    { pos: sy1, label: 'Bottom Spine Safe' },
    { pos: bsy1, label: 'Bottom Safe Margin' },
    { pos: ty1, label: 'Bottom Book Edge' },
    { pos: by1, label: 'Bottom Bleed' },
  ];

  return { vTargets, hTargets };
}

function findClosestTarget(value, targets, maxTol) {
  let best = null;
  let bestAbs = maxTol;
  for (const t of targets) {
    const diff = t.pos - value;
    const ad = Math.abs(diff);
    if (ad <= bestAbs) {
      bestAbs = ad;
      best = { pos: t.pos, label: t.label, delta: diff, absDiff: ad };
    }
  }
  return best;
}

function shouldSnap(e) {
  // Snapping is only needed when zoomed out (< 75%), unless Alt is held to bypass
  return !e.altKey && Boolean(state.guidelines) && state.zoom < 0.75;
}

function hitTestLayer(pt) {
  for (let i = state.layers.length - 1; i >= 0; i--) {
    const l = state.layers[i];
    if (!l.visible) continue;
    if (pt.x >= l.x && pt.x <= l.x + l.w && pt.y >= l.y && pt.y <= l.y + l.h) {
      return l;
    }
  }
  return null;
}

function bindCanvasInteractions() {
  const canvas = document.getElementById('studio-canvas');
  const stage = document.getElementById('canvas-stage');

  window.addEventListener('keydown', (e) => {
    if (e.target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;

    if (e.key === 'Enter' && state.toolMode === 'crop') {
      e.preventDefault();
      exitCropMode(true);
      return;
    }
    if (e.key === 'Escape' && state.toolMode === 'crop') {
      e.preventDefault();
      exitCropMode(false);
      return;
    }
    if (e.code === 'Space') {
      state.isSpaceDown = true;
      canvas.style.cursor = 'grab';
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      undoAction();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
      e.preventDefault();
      redoAction();
    } else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
      const sel = getSelectedLayers();
      if (sel.length > 0 && state.viewMode === 'canvas' && state.toolMode !== 'crop') {
        e.preventDefault();
        pushUndoSnapshot();
        const step = e.shiftKey ? 10 : 1;
        const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
        const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0;
        sel.forEach((l) => {
          l.x += dx;
          l.y += dy;
        });
        syncLayerListUI();
        updateLiveSpineTelemetry();
        renderCanvas();
      }
    }
  });

  window.addEventListener('keyup', (e) => {
    if (e.code === 'Space') {
      state.isSpaceDown = false;
      canvas.style.cursor = 'default';
    }
  });

  // Mouse Wheel Zoom inside Canvas Stage (1.06x = 6% per step — half of 12%)
  stage.addEventListener(
    'wheel',
    (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) {
        e.preventDefault();
        if (e.deltaY === 0) return;
        const factor = e.deltaY < 0 ? 1.06 : 1 / 1.06;
        const base = state.targetZoom || state.zoom;
        setZoom(base * factor);
      }
    },
    { passive: false }
  );

  // Double-click any layer on canvas to immediately enter Canva-style Crop Mode!
  canvas.addEventListener('dblclick', (e) => {
    if (state.viewMode !== 'canvas') return;
    const pt = getCanvasCoords(e);
    const hit = hitTestLayer(pt);
    if (hit) {
      enterCropMode(hit);
    }
  });

  canvas.addEventListener('mousedown', (e) => {
    const pt = getCanvasCoords(e);

    // 1. Hand Pan Mode (or Spacebar held or Middle mouse button)
    if (state.toolMode === 'pan' || state.isSpaceDown || e.button === 1) {
      state.interaction = {
        type: 'pan',
        startClientX: e.clientX,
        startClientY: e.clientY,
        startScrollLeft: stage.scrollLeft,
        startScrollTop: stage.scrollTop,
      };
      canvas.style.cursor = 'grabbing';
      return;
    }

    // 2. Source Spread Divide Mode: drag Left or Right Spine Line
    if (state.viewMode === 'divide' && state.sourceSpread) {
      const tol = 16 / Math.max(0.1, state.zoom);
      if (Math.abs(pt.x - state.sourceSpread.x_left) <= tol) {
        state.interaction = { type: 'divide_left' };
        return;
      }
      if (Math.abs(pt.x - state.sourceSpread.x_right) <= tol) {
        state.interaction = { type: 'divide_right' };
        return;
      }
      return;
    }

    if (state.viewMode !== 'canvas') return;

    // 3. Dedicated Canva-Style CROP MODE interaction
    if (state.toolMode === 'crop' && state.cropSession) {
      const lyr = state.layers.find((l) => l.id === state.cropSession.layerId);
      if (!lyr) {
        exitCropMode(false);
        return;
      }
      const cropBbox = { x: lyr.x, y: lyr.y, w: lyr.w, h: lyr.h };
      const handle = hitTestHandles(pt, cropBbox);
      if (handle) {
        state.interaction = {
          type: 'crop_window_handle',
          handle,
          startPt: pt,
          startCropBox: { x: lyr.x, y: lyr.y, w: lyr.w, h: lyr.h },
          session: { ...state.cropSession },
          layerRef: lyr,
        };
        return;
      }
      // Dragging inside the crop box slides the underlying full image within the stationary crop box!
      if (
        pt.x >= lyr.x &&
        pt.x <= lyr.x + lyr.w &&
        pt.y >= lyr.y &&
        pt.y <= lyr.y + lyr.h
      ) {
        state.interaction = {
          type: 'crop_pan_image',
          startPt: pt,
          startFullX: state.cropSession.fullX,
          startFullY: state.cropSession.fullY,
          layerRef: lyr,
        };
        return;
      }
      // Clicking outside the crop area commits and exits crop mode
      exitCropMode(true);
      return;
    }

    // 4. Normal Select / Resize Handle check
    const sel = getSelectedLayers();
    const bbox = getSelectionBoundingBox(sel);
    const handle = hitTestHandles(pt, bbox);

    if (handle && sel.length > 0) {
      pushUndoSnapshot();
      state.interaction = {
        type: 'resize_handle',
        handle,
        startPt: pt,
        startBbox: { ...bbox },
        startLayers: sel.map((l) => ({
          ref: l,
          x: l.x,
          y: l.y,
          w: l.w,
          h: l.h,
        })),
      };
      return;
    }

    // 5. Hit test layers for selection / drag-move
    const hit = hitTestLayer(pt);
    if (hit) {
      if (e.shiftKey) {
        if (state.selectedIds.includes(hit.id)) {
          state.selectedIds = state.selectedIds.filter((id) => id !== hit.id);
        } else {
          state.selectedIds.push(hit.id);
        }
      } else if (!state.selectedIds.includes(hit.id)) {
        if (hit.group_id) {
          state.selectedIds = state.layers
            .filter((l) => l.group_id === hit.group_id && l.visible)
            .map((l) => l.id);
        } else {
          state.selectedIds = [hit.id];
        }
      }

      syncLayerListUI();
      const activeSel = getSelectedLayers();
      const activeBbox = getSelectionBoundingBox(activeSel);
      pushUndoSnapshot();
      state.interaction = {
        type: 'move',
        startPt: pt,
        startBbox: { ...activeBbox },
        startLayers: activeSel.map((l) => ({
          ref: l,
          x: l.x,
          y: l.y,
        })),
      };
      renderCanvas();
    } else {
      state.selectedIds = [];
      syncLayerListUI();
      renderCanvas();
    }
  });

  window.addEventListener('mousemove', (e) => {
    const pt = getCanvasCoords(e);
    updateCursorFooter(pt);

    if (!state.interaction) {
      updateHoverCursor(pt);
      return;
    }

    const act = state.interaction;

    if (act.type === 'pan') {
      stage.scrollLeft = act.startScrollLeft - (e.clientX - act.startClientX);
      stage.scrollTop = act.startScrollTop - (e.clientY - act.startClientY);
      return;
    }

    if (act.type === 'divide_left' && state.sourceSpread) {
      state.sourceSpread.x_left = Math.max(
        20,
        Math.min(state.sourceSpread.x_right - 15, Math.round(pt.x))
      );
      renderCanvas();
      return;
    }

    if (act.type === 'divide_right' && state.sourceSpread) {
      state.sourceSpread.x_right = Math.min(
        state.sourceSpread.width - 20,
        Math.max(state.sourceSpread.x_left + 15, Math.round(pt.x))
      );
      renderCanvas();
      return;
    }

    // Dedicated Canva-Style Crop Window Handle Drag (Image stays stationary, orange crop window trims/reveals!)
    if (act.type === 'crop_window_handle') {
      const lyr = act.layerRef;
      const cs = state.cropSession;
      const sb = act.startCropBox;
      const h = act.handle;
      const dx = pt.x - act.startPt.x;
      const dy = pt.y - act.startPt.y;
      state.snapLines = [];

      let leftEdge = sb.x;
      let rightEdge = sb.x + sb.w;
      let topEdge = sb.y;
      let bottomEdge = sb.y + sb.h;
      const minCropSize = 24;

      if (h.includes('w')) {
        leftEdge = Math.max(cs.fullX, Math.min(rightEdge - minCropSize, sb.x + dx));
      }
      if (h.includes('e')) {
        rightEdge = Math.min(cs.fullX + cs.fullW, Math.max(leftEdge + minCropSize, sb.x + sb.w + dx));
      }
      if (h.includes('n')) {
        topEdge = Math.max(cs.fullY, Math.min(bottomEdge - minCropSize, sb.y + dy));
      }
      if (h.includes('s')) {
        bottomEdge = Math.min(cs.fullY + cs.fullH, Math.max(topEdge + minCropSize, sb.y + sb.h + dy));
      }

      if (shouldSnap(e)) {
        const snapTol = 10 / Math.max(0.08, state.zoom);
        const { vTargets, hTargets } = getSkeletalSnapTargets();
        if (h.includes('w')) {
          const sv = findClosestTarget(leftEdge, vTargets, snapTol);
          if (sv && sv.pos >= cs.fullX && sv.pos <= rightEdge - minCropSize) {
            leftEdge = sv.pos;
            state.snapLines.push({ type: 'v', pos: sv.pos, label: sv.label });
          }
        }
        if (h.includes('e')) {
          const sv = findClosestTarget(rightEdge, vTargets, snapTol);
          if (sv && sv.pos <= cs.fullX + cs.fullW && sv.pos >= leftEdge + minCropSize) {
            rightEdge = sv.pos;
            state.snapLines.push({ type: 'v', pos: sv.pos, label: sv.label });
          }
        }
        if (h.includes('n')) {
          const sh = findClosestTarget(topEdge, hTargets, snapTol);
          if (sh && sh.pos >= cs.fullY && sh.pos <= bottomEdge - minCropSize) {
            topEdge = sh.pos;
            state.snapLines.push({ type: 'h', pos: sh.pos, label: sh.label });
          }
        }
        if (h.includes('s')) {
          const sh = findClosestTarget(bottomEdge, hTargets, snapTol);
          if (sh && sh.pos <= cs.fullY + cs.fullH && sh.pos >= topEdge + minCropSize) {
            bottomEdge = sh.pos;
            state.snapLines.push({ type: 'h', pos: sh.pos, label: sh.label });
          }
        }
      }

      lyr.x = leftEdge;
      lyr.y = topEdge;
      lyr.w = rightEdge - leftEdge;
      lyr.h = bottomEdge - topEdge;

      // Convert crop box edges back to source-image pixel crop values
      lyr.crop.left = Math.max(0, (leftEdge - cs.fullX) / cs.scaleX);
      lyr.crop.right = Math.max(0, (cs.fullX + cs.fullW - rightEdge) / cs.scaleX);
      lyr.crop.top = Math.max(0, (topEdge - cs.fullY) / cs.scaleY);
      lyr.crop.bottom = Math.max(0, (cs.fullY + cs.fullH - bottomEdge) / cs.scaleY);

      syncLayerListUI();
      renderCanvas();
      return;
    }

    // Panning the full image inside the stationary crop window
    if (act.type === 'crop_pan_image') {
      const lyr = act.layerRef;
      const cs = state.cropSession;
      const dx = pt.x - act.startPt.x;
      const dy = pt.y - act.startPt.y;

      // Clamp fullX / fullY so the crop window stays inside the full image
      const minFullX = lyr.x + lyr.w - cs.fullW;
      const maxFullX = lyr.x;
      const minFullY = lyr.y + lyr.h - cs.fullH;
      const maxFullY = lyr.y;

      cs.fullX = Math.max(minFullX, Math.min(maxFullX, act.startFullX + dx));
      cs.fullY = Math.max(minFullY, Math.min(maxFullY, act.startFullY + dy));

      lyr.crop.left = Math.max(0, (lyr.x - cs.fullX) / cs.scaleX);
      lyr.crop.right = Math.max(0, (cs.fullX + cs.fullW - (lyr.x + lyr.w)) / cs.scaleX);
      lyr.crop.top = Math.max(0, (lyr.y - cs.fullY) / cs.scaleY);
      lyr.crop.bottom = Math.max(0, (cs.fullY + cs.fullH - (lyr.y + lyr.h)) / cs.scaleY);

      renderCanvas();
      return;
    }

    if (act.type === 'move') {
      let dx = pt.x - act.startPt.x;
      let dy = pt.y - act.startPt.y;
      state.snapLines = [];

      if (shouldSnap(e)) {
        const snapTol = 10 / Math.max(0.08, state.zoom);
        const { vTargets, hTargets } = getSkeletalSnapTargets();

        // 1. Vertical skeletal direct fit (Left edge, Center X, Right edge)
        const candLeft = act.startBbox.x + dx;
        const candCenterX = candLeft + act.startBbox.w / 2.0;
        const candRight = candLeft + act.startBbox.w;

        const vCandidates = [
          findClosestTarget(candLeft, vTargets, snapTol),
          findClosestTarget(candCenterX, vTargets, snapTol),
          findClosestTarget(candRight, vTargets, snapTol),
        ].filter(Boolean);

        if (vCandidates.length > 0) {
          vCandidates.sort((a, b) => a.absDiff - b.absDiff);
          const bestV = vCandidates[0];
          dx += bestV.delta;
          state.snapLines.push({ type: 'v', pos: bestV.pos, label: bestV.label });
        }

        // 2. Horizontal skeletal direct fit (Top edge, Middle Y, Bottom edge)
        const candTop = act.startBbox.y + dy;
        const candCenterY = candTop + act.startBbox.h / 2.0;
        const candBottom = candTop + act.startBbox.h;

        const hCandidates = [
          findClosestTarget(candTop, hTargets, snapTol),
          findClosestTarget(candCenterY, hTargets, snapTol),
          findClosestTarget(candBottom, hTargets, snapTol),
        ].filter(Boolean);

        if (hCandidates.length > 0) {
          hCandidates.sort((a, b) => a.absDiff - b.absDiff);
          const bestH = hCandidates[0];
          dy += bestH.delta;
          state.snapLines.push({ type: 'h', pos: bestH.pos, label: bestH.label });
        }
      }

      act.startLayers.forEach((item) => {
        item.ref.x = item.x + dx;
        item.ref.y = item.y + dy;
      });
      syncLayerListUI();
      updateLiveSpineTelemetry();
      renderCanvas();
      return;
    }

    if (act.type === 'resize_handle') {
      const h = act.handle;
      const sb = act.startBbox;
      state.snapLines = [];

      const dx = pt.x - act.startPt.x;
      const dy = pt.y - act.startPt.y;
      const minSize = 8;

      let leftEdge = sb.x;
      let rightEdge = sb.x + sb.w;
      let topEdge = sb.y;
      let bottomEdge = sb.y + sb.h;

      if (h.includes('e')) rightEdge = Math.max(leftEdge + minSize, sb.x + sb.w + dx);
      if (h.includes('s')) bottomEdge = Math.max(topEdge + minSize, sb.y + sb.h + dy);
      if (h.includes('w')) leftEdge = Math.min(rightEdge - minSize, sb.x + dx);
      if (h.includes('n')) topEdge = Math.min(bottomEdge - minSize, sb.y + dy);

      let snappedX = false;
      let snappedY = false;

      if (shouldSnap(e)) {
        const snapTol = 10 / Math.max(0.08, state.zoom);
        const { vTargets, hTargets } = getSkeletalSnapTargets();

        if (h.includes('w')) {
          const sv = findClosestTarget(leftEdge, vTargets, snapTol);
          if (sv && sv.pos <= rightEdge - minSize) {
            leftEdge = sv.pos;
            snappedX = true;
            state.snapLines.push({ type: 'v', pos: sv.pos, label: sv.label });
          }
        }
        if (h.includes('e')) {
          const sv = findClosestTarget(rightEdge, vTargets, snapTol);
          if (sv && sv.pos >= leftEdge + minSize) {
            rightEdge = sv.pos;
            snappedX = true;
            state.snapLines.push({ type: 'v', pos: sv.pos, label: sv.label });
          }
        }
        if (h.includes('n')) {
          const sh = findClosestTarget(topEdge, hTargets, snapTol);
          if (sh && sh.pos <= bottomEdge - minSize) {
            topEdge = sh.pos;
            snappedY = true;
            state.snapLines.push({ type: 'h', pos: sh.pos, label: sh.label });
          }
        }
        if (h.includes('s')) {
          const sh = findClosestTarget(bottomEdge, hTargets, snapTol);
          if (sh && sh.pos >= topEdge + minSize) {
            bottomEdge = sh.pos;
            snappedY = true;
            state.snapLines.push({ type: 'h', pos: sh.pos, label: sh.label });
          }
        }
      }

      let newX = leftEdge;
      let newY = topEdge;
      let newW = rightEdge - leftEdge;
      let newH = bottomEdge - topEdge;

      const lockAspect =
        e.shiftKey || act.startLayers.some((item) => item.ref.lock_aspect);
      if (lockAspect && h.length === 2) {
        const aspect = sb.w / Math.max(1, sb.h);
        const preferX = snappedX && !snappedY ? true : snappedY && !snappedX ? false : Math.abs(dx) > Math.abs(dy);
        if (preferX) {
          newH = newW / aspect;
          if (h.includes('n')) newY = sb.y + sb.h - newH;
        } else {
          newW = newH * aspect;
          if (h.includes('w')) newX = sb.x + sb.w - newW;
        }
      }

      const scaleX = newW / Math.max(1, sb.w);
      const scaleY = newH / Math.max(1, sb.h);

      act.startLayers.forEach((item) => {
        item.ref.x = newX + (item.x - sb.x) * scaleX;
        item.ref.y = newY + (item.y - sb.y) * scaleY;
        item.ref.w = Math.max(4, item.w * scaleX);
        item.ref.h = Math.max(4, item.h * scaleY);
      });

      syncLayerListUI();
      updateLiveSpineTelemetry();
      renderCanvas();
    }
  });

  window.addEventListener('mouseup', () => {
    if (state.interaction) {
      state.interaction = null;
      state.snapLines = [];
      renderCanvas();
    }
  });
}

function updateHoverCursor(pt) {
  const canvas = document.getElementById('studio-canvas');
  if (state.toolMode === 'pan' || state.isSpaceDown) {
    canvas.style.cursor = 'grab';
    return;
  }
  if (state.viewMode === 'divide' && state.sourceSpread) {
    const tol = 16 / Math.max(0.1, state.zoom);
    if (
      Math.abs(pt.x - state.sourceSpread.x_left) <= tol ||
      Math.abs(pt.x - state.sourceSpread.x_right) <= tol
    ) {
      canvas.style.cursor = 'ew-resize';
    } else {
      canvas.style.cursor = 'default';
    }
    return;
  }

  const sel = getSelectedLayers();
  const bbox = getSelectionBoundingBox(sel);
  const h = hitTestHandles(pt, bbox);
  if (h) {
    const handles = getHandlePositions(bbox);
    canvas.style.cursor = handles[h].cursor;
    return;
  }
  const hit = hitTestLayer(pt);
  canvas.style.cursor = hit ? 'move' : 'default';
}

function updateCursorFooter(pt) {
  const { templateW, templateH } = getActiveCanvasPhysicalSize();
  const dpi = state.guidelines ? state.guidelines.dpi : 300;
  const xPx = Math.round(pt.x);
  const yPx = Math.round(pt.y);
  const xIn = (xPx / dpi).toFixed(2);
  const yIn = (yPx / dpi).toFixed(2);
  const isOutside = xPx < 0 || yPx < 0 || xPx > templateW || yPx > templateH;
  const zoneTag = isOutside ? ' (In Grey Margin — Won’t Print)' : '';
  document.getElementById('cursor-coords').textContent =
    `Position: ${xIn}", ${yIn}" (${xPx}, ${yPx} px)${zoneTag} · Double-click any part to Crop`;
}

/* ==========================================================================
   8. Real-Time 60 FPS Spine Clearance & Print Check Telemetry
   ========================================================================== */

function updateLiveSpineTelemetry() {
  if (!state.guidelines) return;
  const xFL = state.guidelines.spine_creases.calculated_x_left;
  const xFR = state.guidelines.spine_creases.calculated_x_right;
  const safeMarginPx = state.guidelines.margins.spine_safe_margin_px;

  const badge = document.getElementById('status-badge');
  if (state.layers.length === 0) {
    badge.textContent = 'TEMPLATE READY';
    badge.className = 'badge badge-ready';
    return;
  }

  const spineLayers = state.layers.filter(
    (l) => l.visible && (l.kind === 'spine_text' || l.kind === 'spine_ornament')
  );
  if (spineLayers.length === 0) {
    badge.textContent = 'PRINT READY';
    badge.className = 'badge badge-pass';
    return;
  }

  let minGlyphX = Infinity;
  let maxGlyphX = -Infinity;
  spineLayers.forEach((l) => {
    const gl = l.x + l.w * (l.glyph_left_ratio ?? 0.0);
    const gr = l.x + l.w * (l.glyph_right_ratio ?? 1.0);
    minGlyphX = Math.min(minGlyphX, gl);
    maxGlyphX = Math.max(maxGlyphX, gr);
  });

  const leftGap = minGlyphX - xFL;
  const rightGap = xFR - maxGlyphX;
  const isSafe = leftGap >= safeMarginPx - 0.2 && rightGap >= safeMarginPx - 0.2;
  const optCenter = (minGlyphX + maxGlyphX) / 2.0 - xFL;
  const geomCenter = (xFR - xFL) / 2.0;
  const deltaCenter = optCenter - geomCenter;

  badge.textContent = isSafe ? 'PRINT READY ✓' : 'SPINE TEXT TOO WIDE';
  badge.className = `badge ${isSafe ? 'badge-pass' : 'badge-fail'}`;

  const elSafe = document.getElementById('diag-spine-safe');
  elSafe.textContent = isSafe ? 'Fits Inside Spine ✓' : 'Touches Spine Fold!';
  elSafe.className = `diag-val ${isSafe ? 'pass' : 'fail'}`;

  const elLeft = document.getElementById('diag-left-clear');
  elLeft.textContent = `${leftGap.toFixed(1)} px (need ${safeMarginPx.toFixed(1)} px)`;
  elLeft.className = `diag-val ${leftGap >= safeMarginPx - 0.2 ? 'pass' : 'fail'}`;

  const elRight = document.getElementById('diag-right-clear');
  elRight.textContent = `${rightGap.toFixed(1)} px (need ${safeMarginPx.toFixed(1)} px)`;
  elRight.className = `diag-val ${rightGap >= safeMarginPx - 0.2 ? 'pass' : 'fail'}`;

  const elShift = document.getElementById('diag-opt-shift');
  elShift.textContent =
    Math.abs(deltaCenter) <= 1.5
      ? 'Centered ✓'
      : `${deltaCenter >= 0 ? '+' : ''}${deltaCenter.toFixed(1)} px off-center`;
  elShift.className = `diag-val ${Math.abs(deltaCenter) <= 3.0 ? 'pass' : 'warn'}`;
}

function updateSidebarMetrics() {
  if (!state.spec || !state.guidelines) return;
  const s = state.spec;
  const g = state.guidelines;
  const sc = g.spine_creases;

  document.getElementById('header-dims').textContent =
    `Full Cover: ${s.total_w_in.toFixed(3)}" × ${s.total_h_in.toFixed(3)}" · Spine: ${s.spine_w_in.toFixed(3)}"`;

  document.getElementById('spec-total-dim').textContent =
    `${s.total_w_in.toFixed(3)}" × ${s.total_h_in.toFixed(3)}"`;
  document.getElementById('spec-pixel-dim').textContent =
    `${g.width_px} × ${g.height_px} px`;
  document.getElementById('spec-spine-w').textContent =
    `${s.spine_w_in.toFixed(3)}" (${Math.round(sc.calculated_x_right - sc.calculated_x_left)} px)`;
  document.getElementById('spec-fold-x').textContent =
    `${Math.round(sc.calculated_x_left)} / ${Math.round(sc.calculated_x_right)} px`;

  if (s.binding === 'casewrap') {
    document.getElementById('spec-bleed').textContent =
      `Wrap ${s.wrap_in.toFixed(3)}" + Hinge ${s.hinge_in.toFixed(3)}"`;
  } else {
    document.getElementById('spec-bleed').textContent =
      `${s.bleed_in.toFixed(3)}" (${Math.round(s.bleed_in * g.dpi)} px)`;
  }

  document.getElementById('spec-spine-safe').textContent =
    `${g.margins.spine_safe_margin_in.toFixed(4)}" (${g.margins.spine_safe_margin_px.toFixed(1)} px)`;

  const spineBanner = document.getElementById('spine-warning-banner');
  spineBanner.classList.toggle('hidden', Boolean(s.allow_spine_text));

  if (state.preflight && state.preflight.effective_dpi) {
    const elDpi = document.getElementById('diag-dpi');
    elDpi.textContent = `${state.preflight.effective_dpi} DPI`;
    elDpi.className = `diag-val ${state.preflight.effective_dpi >= 250 ? 'pass' : 'warn'}`;

    const elTac = document.getElementById('diag-tac');
    elTac.textContent = `${state.preflight.max_tac_pct}%`;
    elTac.className = `diag-val ${state.preflight.tac_pass ? 'pass' : 'fail'}`;
  }

  updateLiveSpineTelemetry();
}

/* ==========================================================================
   9. HTML5 Canvas Rendering Engine with Pasteboard & Canva Crop Overlay
   ========================================================================== */

function renderCanvas() {
  const canvas = document.getElementById('studio-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // Mode B: Adjust Spine Split on Source Image
  if (state.viewMode === 'divide' && state.sourceSpread) {
    renderSourceDivideCanvas(canvas, ctx);
    return;
  }

  if (!state.guidelines) return;
  const g = state.guidelines;
  const W = g.width_px;
  const H = g.height_px;
  const pad = PASTEBOARD_PAD;
  const physW = W + pad * 2;
  const physH = H + pad * 2;

  if (canvas.width !== physW || canvas.height !== physH) {
    canvas.width = physW;
    canvas.height = physH;
    canvas.style.width = `${Math.round(physW * state.zoom)}px`;
    canvas.style.height = `${Math.round(physH * state.zoom)}px`;
  }

  ctx.save();
  ctx.clearRect(0, 0, physW, physH);

  // 1. Fill entire canvas (including pasteboard) with soft light-slate pasteboard tone
  ctx.fillStyle = '#cbd5e1';
  ctx.fillRect(0, 0, physW, physH);

  // Translate origin so (0, 0) .. (W, H) is the exact Print Skeleton
  ctx.translate(pad, pad);

  // 2. Fill active Print Skeleton area [0, 0, W, H] with clean paper white + drop shadow
  ctx.save();
  ctx.shadowColor = 'rgba(15, 23, 42, 0.18)';
  ctx.shadowBlur = 32;
  ctx.shadowOffsetY = 8;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, W, H);
  ctx.restore();

  const sc = g.spine_creases;
  const xFoldLeft = sc.calculated_x_left;
  const xFoldRight = sc.calculated_x_right;

  // If no cover uploaded yet, draw a welcoming author-friendly empty template
  if (state.layers.length === 0) {
    ctx.save();
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(xFoldLeft, 0, xFoldRight - xFoldLeft, H);
    ctx.fillStyle = '#334155';
    ctx.font = `bold ${Math.round(W * 0.017)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('Drop Your Cover Image Here to Start', W / 2, H * 0.46);
    ctx.font = `${Math.round(W * 0.0105)}px sans-serif`;
    ctx.fillStyle = '#64748b';
    ctx.fillText(
      'Or use "Cover Artwork" on the left — Back, Spine & Front will be split automatically',
      W / 2,
      H * 0.505
    );
    ctx.restore();
  }

  // 3. Draw all visible layers (including parts that extend into the pasteboard outside 0..W, 0..H!)
  state.layers.forEach((lyr) => {
    if (!lyr.visible || !lyr.img) return;

    // If this layer is currently being cropped in Crop Mode, draw the dimmed full image first!
    if (state.toolMode === 'crop' && state.cropSession && state.cropSession.layerId === lyr.id) {
      const cs = state.cropSession;
      ctx.save();
      ctx.globalAlpha = 0.32;
      ctx.drawImage(lyr.img, 0, 0, lyr.natW, lyr.natH, cs.fullX, cs.fullY, cs.fullW, cs.fullH);
      ctx.restore();
    }

    const c = lyr.crop || { top: 0, right: 0, bottom: 0, left: 0 };
    const sx = Math.max(0, c.left);
    const sy = Math.max(0, c.top);
    const sw = Math.max(1, lyr.natW - c.left - c.right);
    const sh = Math.max(1, lyr.natH - c.top - c.bottom);
    ctx.drawImage(lyr.img, sx, sy, sw, sh, lyr.x, lyr.y, lyr.w, lyr.h);
  });

  // 4. Draw Semi-Transparent Grey Pasteboard Mask over the 4 regions OUTSIDE [0, 0, W, H]
  // Any layer extending outside [0, 0, W, H] remains clearly visible through this grey mask and 100% accessible!
  ctx.save();
  ctx.fillStyle = 'rgba(100, 116, 139, 0.48)';
  // Top pasteboard band
  ctx.fillRect(-pad, -pad, W + pad * 2, pad);
  // Bottom pasteboard band
  ctx.fillRect(-pad, H, W + pad * 2, pad);
  // Left pasteboard band
  ctx.fillRect(-pad, 0, pad, H);
  // Right pasteboard band
  ctx.fillRect(W, 0, pad, H);

  // Subtle label in the top grey pasteboard margin
  ctx.fillStyle = '#334155';
  ctx.font = `bold ${Math.max(22, Math.round(W * 0.0085))}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.fillText(
    'Outside Print Area — Grey area won’t print, but parts stay visible here so you can grab or crop them',
    W / 2,
    -pad * 0.22
  );
  ctx.restore();

  // 5. Draw Fixed Target Template Guidelines
  const lw = Math.max(2, Math.round(W / 1100));

  // 5a. Outer Print Edge / Bleed Box (Cyan dashed)
  if (state.overlays.bleed) {
    const [bx0, by0, bx1, by1] = g.bleed_box;
    ctx.save();
    ctx.strokeStyle = '#06b6d4';
    ctx.lineWidth = lw * 1.5;
    ctx.setLineDash([lw * 5, lw * 3]);
    ctx.strokeRect(bx0, by0, bx1 - bx0, by1 - by0);
    ctx.restore();
  }

  // 5b. Final Book Edge / Trim Box (Green solid)
  if (state.overlays.trim) {
    const [tx0, ty0, tx1, ty1] = g.trim_box;
    ctx.save();
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = lw * 1.4;
    ctx.strokeRect(tx0, ty0, tx1 - tx0, ty1 - ty0);
    ctx.restore();
  }

  // 5c. Cover Safe Margins (Orange dashed)
  if (state.overlays.coverSafe) {
    ctx.save();
    ctx.strokeStyle = 'rgba(249, 115, 22, 0.85)';
    ctx.lineWidth = lw;
    ctx.setLineDash([lw * 3, lw * 3]);
    const [bsx0, bsy0, bsx1, bsy1] = g.back_cover_safe_zone;
    ctx.strokeRect(bsx0, bsy0, bsx1 - bsx0, bsy1 - bsy0);
    const [fsx0, fsy0, fsx1, fsy1] = g.front_cover_safe_zone;
    ctx.strokeRect(fsx0, fsy0, fsx1 - fsx0, fsy1 - fsy0);
    ctx.restore();
  }

  // 5d. ISBN Barcode Zone on Back Cover (Yellow dashed)
  if (state.overlays.barcode && g.barcode_zone) {
    const [bcx0, bcy0, bcx1, bcy1] = g.barcode_zone;
    ctx.save();
    ctx.fillStyle = 'rgba(254, 249, 195, 0.72)';
    ctx.fillRect(bcx0, bcy0, bcx1 - bcx0, bcy1 - bcy0);
    ctx.strokeStyle = '#d97706';
    ctx.lineWidth = lw * 1.2;
    ctx.setLineDash([lw * 3, lw * 2]);
    ctx.strokeRect(bcx0, bcy0, bcx1 - bcx0, bcy1 - bcy0);
    ctx.fillStyle = '#92400e';
    ctx.font = `bold ${Math.max(20, Math.round(W * 0.0085))}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText('BARCODE BOX (2.0" × 1.2")', (bcx0 + bcx1) / 2, (bcy0 + bcy1) / 2);
    ctx.restore();
  }

  // 5e. Spine Fold Lines (Blue dashed)
  if (state.overlays.creases) {
    ctx.save();
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = lw * 1.5;
    ctx.setLineDash([lw * 6, lw * 4]);
    ctx.beginPath();
    ctx.moveTo(xFoldLeft, 0);
    ctx.lineTo(xFoldLeft, H);
    ctx.moveTo(xFoldRight, 0);
    ctx.lineTo(xFoldRight, H);
    ctx.stroke();
    ctx.restore();
  }

  // 5f. Spine Text Safe Zone (Pink dashed + center line)
  if (state.overlays.spineSafe) {
    const [sx0, sy0, sx1, sy1] = g.spine_safe_zone;
    ctx.save();
    if (sx1 > sx0) {
      ctx.strokeStyle = '#ec4899';
      ctx.lineWidth = lw * 1.3;
      ctx.setLineDash([lw * 3, lw * 2]);
      ctx.strokeRect(sx0, sy0, sx1 - sx0, sy1 - sy0);

      const spCenter = (xFoldLeft + xFoldRight) / 2.0;
      ctx.strokeStyle = 'rgba(236, 72, 153, 0.45)';
      ctx.lineWidth = Math.max(1, lw * 0.7);
      ctx.setLineDash([lw * 2, lw * 4]);
      ctx.beginPath();
      ctx.moveTo(spCenter, sy0);
      ctx.lineTo(spCenter, sy1);
      ctx.stroke();
    }
    ctx.restore();
  }

  // 5g. Panel Labels
  if (state.overlays.measurements && state.spec) {
    const fontSz = Math.max(22, Math.round(W * 0.01));
    ctx.save();
    ctx.font = `bold ${fontSz}px sans-serif`;
    const drawBadge = (text, x, y, bgColor = 'rgba(15, 23, 42, 0.85)', fgColor = '#f8fafc') => {
      const m = ctx.measureText(text);
      const pw = m.width + fontSz * 0.9;
      const ph = fontSz * 1.55;
      ctx.fillStyle = bgColor;
      ctx.fillRect(x - pw / 2, y - ph / 2, pw, ph);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x - pw / 2, y - ph / 2, pw, ph);
      ctx.fillStyle = fgColor;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, x, y);
    };

    const [tx0, ty0, tx1] = g.trim_box;
    drawBadge(`BACK COVER (${state.spec.trim_w_in}" × ${state.spec.trim_h_in}")`, (tx0 + xFoldLeft) / 2, ty0 + fontSz * 1.8);
    drawBadge(`FRONT COVER (${state.spec.trim_w_in}" × ${state.spec.trim_h_in}")`, (xFoldRight + tx1) / 2, ty0 + fontSz * 1.8);
    drawBadge(`SPINE (${state.spec.spine_w_in.toFixed(2)}")`, (xFoldLeft + xFoldRight) / 2, ty0 + fontSz * 4.0, 'rgba(236, 72, 153, 0.9)', '#fff');
    ctx.restore();
  }

  // 6. Magnetic Snap Alignment Lines (Vertical & Horizontal with Label Badges)
  if (state.snapLines.length > 0) {
    ctx.save();
    const snapFontSz = Math.max(18, Math.round(W * 0.008));
    ctx.font = `bold ${snapFontSz}px sans-serif`;

    state.snapLines.forEach((sl) => {
      ctx.strokeStyle = '#f43f5e';
      ctx.lineWidth = Math.max(2, 2 / Math.max(0.08, state.zoom));
      ctx.setLineDash([lw * 3, lw * 2]);
      ctx.beginPath();
      if (sl.type === 'v') {
        ctx.moveTo(sl.pos, -pad * 0.35);
        ctx.lineTo(sl.pos, H + pad * 0.35);
      } else {
        ctx.moveTo(-pad * 0.35, sl.pos);
        ctx.lineTo(W + pad * 0.35, sl.pos);
      }
      ctx.stroke();

      if (sl.label) {
        ctx.setLineDash([]);
        const tw = ctx.measureText(sl.label).width + snapFontSz * 0.8;
        const th = snapFontSz * 1.45;
        const bx = sl.type === 'v' ? sl.pos : W * 0.5;
        const by = sl.type === 'v' ? -th * 0.85 : sl.pos;
        ctx.fillStyle = '#f43f5e';
        ctx.fillRect(bx - tw / 2, by - th / 2, tw, th);
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(sl.label, bx, by);
      }
    });
    ctx.restore();
  }

  // 7. Draw Active Selection or Canva-Style Crop Handles ON TOP of everything (even in the pasteboard!)
  const sel = getSelectedLayers();
  const bbox = getSelectionBoundingBox(sel);
  if (bbox) {
    ctx.save();
    const isCrop = state.toolMode === 'crop' && state.cropSession;

    if (isCrop) {
      // Draw dashed outline around the full uncropped image so the user sees its full extent
      const cs = state.cropSession;
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.45)';
      ctx.lineWidth = Math.max(1.5, 1.5 / Math.max(0.08, state.zoom));
      ctx.setLineDash([lw * 3, lw * 3]);
      ctx.strokeRect(cs.fullX, cs.fullY, cs.fullW, cs.fullH);

      // Draw Rule-of-Thirds grid inside the active crop window
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.35)';
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(bbox.x + bbox.w / 3, bbox.y);
      ctx.lineTo(bbox.x + bbox.w / 3, bbox.y + bbox.h);
      ctx.moveTo(bbox.x + (bbox.w * 2) / 3, bbox.y);
      ctx.lineTo(bbox.x + (bbox.w * 2) / 3, bbox.y + bbox.h);
      ctx.moveTo(bbox.x, bbox.y + bbox.h / 3);
      ctx.lineTo(bbox.x + bbox.w, bbox.y + bbox.h / 3);
      ctx.moveTo(bbox.x, bbox.y + (bbox.h * 2) / 3);
      ctx.lineTo(bbox.x + bbox.w, bbox.y + (bbox.h * 2) / 3);
      ctx.stroke();
    } else if (sel.length > 1) {
      ctx.strokeStyle = 'rgba(96, 165, 250, 0.65)';
      ctx.lineWidth = Math.max(1.2, lw * 0.8);
      ctx.setLineDash([lw * 2, lw * 2]);
      sel.forEach((l) => {
        ctx.strokeRect(l.x, l.y, l.w, l.h);
      });
    }

    const boxColor = isCrop ? '#f59e0b' : '#3b82f6';
    ctx.strokeStyle = boxColor;
    ctx.lineWidth = Math.max(1.5, 1.6 / Math.max(0.08, state.zoom));
    ctx.setLineDash([]);
    ctx.strokeRect(bbox.x, bbox.y, bbox.w, bbox.h);

    // Draw 8 Small, Circular, Zoom-Adaptive Handles
    const r = getHandleRadiusCanvas(bbox);
    const handles = getHandlePositions(bbox);
    Object.entries(handles).forEach(([, hPt]) => {
      ctx.fillStyle = isCrop ? '#f59e0b' : '#ffffff';
      ctx.strokeStyle = isCrop ? '#ffffff' : boxColor;
      ctx.lineWidth = Math.max(1.2, 1.5 / Math.max(0.08, state.zoom));
      ctx.beginPath();
      ctx.arc(hPt.x, hPt.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    });
    ctx.restore();
  }

  ctx.restore();
}

function renderSourceDivideCanvas(canvas, ctx) {
  const sp = state.sourceSpread;
  const W = sp.width;
  const H = sp.height;

  if (canvas.width !== W || canvas.height !== H) {
    canvas.width = W;
    canvas.height = H;
    canvas.style.width = `${Math.round(W * state.zoom)}px`;
    canvas.style.height = `${Math.round(H * state.zoom)}px`;
  }

  ctx.clearRect(0, 0, W, H);
  ctx.drawImage(sp.img, 0, 0, W, H);

  ctx.fillStyle = 'rgba(59, 130, 246, 0.14)';
  ctx.fillRect(0, 0, sp.x_left, H);

  ctx.fillStyle = 'rgba(236, 72, 153, 0.24)';
  ctx.fillRect(sp.x_left, 0, sp.x_right - sp.x_left, H);

  ctx.fillStyle = 'rgba(16, 185, 129, 0.14)';
  ctx.fillRect(sp.x_right, 0, W - sp.x_right, H);

  ctx.save();
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(sp.x_left, 0);
  ctx.lineTo(sp.x_left, H);
  ctx.stroke();

  ctx.strokeStyle = '#ec4899';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(sp.x_right, 0);
  ctx.lineTo(sp.x_right, H);
  ctx.stroke();

  ctx.font = 'bold 14px sans-serif';
  ctx.fillStyle = '#06b6d4';
  ctx.fillRect(sp.x_left - 125, 18, 120, 28);
  ctx.fillStyle = '#000';
  ctx.textAlign = 'center';
  ctx.fillText(`◀ Left Spine (${sp.x_left}px)`, sp.x_left - 65, 36);

  ctx.fillStyle = '#ec4899';
  ctx.fillRect(sp.x_right + 5, 18, 125, 28);
  ctx.fillStyle = '#fff';
  ctx.fillText(`Right Spine (${sp.x_right}px) ▶`, sp.x_right + 67, 36);
  ctx.restore();
}

/* ==========================================================================
   10. Full-Resolution Offscreen Layer Compositor & Export Trigger
   ========================================================================== */

function compositeCleanSpreadBlob() {
  return new Promise((resolve) => {
    if (!state.guidelines || state.layers.length === 0) {
      resolve(null);
      return;
    }
    const W = state.guidelines.width_px;
    const H = state.guidelines.height_px;
    const offCanvas = document.createElement('canvas');
    offCanvas.width = W;
    offCanvas.height = H;
    const ctx = offCanvas.getContext('2d');

    ctx.fillStyle = '#2d3723';
    ctx.fillRect(0, 0, W, H);

    state.layers.forEach((lyr) => {
      if (!lyr.visible || !lyr.img) return;
      const c = lyr.crop || { top: 0, right: 0, bottom: 0, left: 0 };
      const sx = Math.max(0, c.left);
      const sy = Math.max(0, c.top);
      const sw = Math.max(1, lyr.natW - c.left - c.right);
      const sh = Math.max(1, lyr.natH - c.top - c.bottom);
      ctx.drawImage(lyr.img, sx, sy, sw, sh, lyr.x, lyr.y, lyr.w, lyr.h);
    });

    offCanvas.toBlob((blob) => resolve(blob), 'image/png');
  });
}

async function triggerExport(format) {
  if (state.toolMode === 'crop') exitCropMode(true);
  const btnMap = {
    pdf: 'btn-export-pdf',
    png: 'btn-export-png',
    jpg: 'btn-export-jpg',
    zip: 'btn-export-zip',
  };
  const btn = document.getElementById(btnMap[format]);
  const origText = btn.textContent;
  btn.textContent = 'Preparing...';
  btn.disabled = true;
  showLoading(`Generating print-ready ${format.toUpperCase()} file...`);

  try {
    const fd = buildFormData(false);
    fd.append('format', format);

    const compBlob = await compositeCleanSpreadBlob();
    if (compBlob) {
      fd.append('file_composited', compBlob, 'composited_spread.png');
    }

    const resp = await fetch('/api/export', {
      method: 'POST',
      body: fd,
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || 'Export failed');
    }

    const blob = await resp.blob();
    const contentDisp = resp.headers.get('Content-Disposition') || '';
    let filename = `cover_export.${format}`;
    const match = contentDisp.match(/filename="([^"]+)"/);
    if (match && match[1]) {
      filename = match[1];
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error('Export error:', err);
  } finally {
    btn.textContent = origText;
    btn.disabled = false;
    hideLoading();
  }
}
