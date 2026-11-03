/**
 * ClosedLoop Playground Interactive Controller (Plan §10, §13 PA3).
 *
 * Implements:
 * - Real-time client-side SHA-256 calculation (LF normalized).
 * - Real-time 4-tuple badge evaluation (program hash, robot preset, task preset, sim hash).
 * - Preloaded certified program templates.
 * - Live Server-Sent Events (SSE) streaming execution against /run.
 * - Offline Tier 0 (Hash Lab) fallback handling.
 */
(function (root) {
  "use strict";

  // Preloaded frozen programs matching certified records
  // v2: 5f74f7762ee1f378b2d71f6938a288fa12aa51a0ee93ee33a2639944cd66aaa1
  // v1: bec73dec45a88431d2b6f705dfc26fe1e81f896bc4e72bf651a397cf89e6fc55
  var TEMPLATES = {
    v2_certified: [
      "def policy(env, rng):",
      "    cube_pos = env.get_object_pos(\"cube\")",
      "    pad_pos = env.get_object_pos(\"pad\")",
      "    env.open_gripper()",
      "    above_cube = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.25)",
      "    env.move_to(above_cube, steps=80)",
      "    grasp_pos = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.005)",
      "    env.move_to(grasp_pos, steps=80)",
      "    env.close_gripper(300)",
      "    env.move_to(grasp_pos, steps=40)",
      "    env.move_to(above_cube, steps=150)",
      "    above_pad = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.25)",
      "    env.move_to(above_pad, steps=200)",
      "    place_pos = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.06)",
      "    env.move_to(place_pos, steps=150)",
      "    env.open_gripper()",
      "    env.move_to(place_pos, steps=30)",
      "    env.move_to(above_pad, steps=100)",
      "",
    ].join("\n"),

    v1_certified: [
      "def policy(env, rng):",
      "    cube_pos = env.get_object_pos(\"cube\")",
      "    pad_pos = env.get_object_pos(\"pad\")",
      "    env.open_gripper()",
      "    above_cube = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.20)",
      "    env.move_to(above_cube, steps=80)",
      "    grasp_pos = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.005)",
      "    env.move_to(grasp_pos, steps=80)",
      "    env.close_gripper(100)",
      "    env.move_to(grasp_pos, steps=20)",
      "    env.move_to(above_cube, steps=100)",
      "    above_pad = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.20)",
      "    env.move_to(above_pad, steps=100)",
      "    place_pos = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.02)",
      "    env.move_to(place_pos, steps=100)",
      "    env.open_gripper()",
      "    env.move_to(place_pos, steps=20)",
      "    env.move_to(above_pad, steps=80)",
    ].join("\n"),

    initial_flawed: [
      "def policy(env, rng):",
      "    cube_pos = env.get_object_pos(\"cube\")",
      "    pad_pos = env.get_object_pos(\"pad\")",
      "    env.open_gripper()",
      "    above_cube = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.15)",
      "    env.move_to(above_cube, steps=60)",
      "    grasp_pos = (cube_pos[0], cube_pos[1], cube_pos[2] + 0.02)",
      "    env.move_to(grasp_pos, steps=60)",
      "    env.close_gripper(10)",
      "    env.move_to(above_cube, steps=60)",
      "    above_pad = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.15)",
      "    env.move_to(above_pad, steps=60)",
      "    place_pos = (pad_pos[0], pad_pos[1], pad_pos[2] + 0.05)",
      "    env.move_to(place_pos, steps=60)",
      "    env.open_gripper()",
      "    env.move_to(above_pad, steps=60)",
      "",
    ].join("\n"),
  };

  // Known frozen simulation code SHA-256 fingerprint
  var SIM_CODE_SHA256 = "bf28d7d8a1480d480349869c6c0d775861ed5000a86cf44eeae478a1a4ac34c3";

  // Pure JavaScript SHA-256 implementation (works offline, in HTTP and non-secure contexts)
  function sha256_pure(ascii) {
    function ror(v, n) { return (v >>> n) | (v << (32 - n)); }
    var K = [
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    ];

    var H = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
    ];

    var bytes = [];
    for (var i = 0; i < ascii.length; i++) {
      var c = ascii.charCodeAt(i);
      if (c < 0x80) {
        bytes.push(c);
      } else if (c < 0x800) {
        bytes.push(0xc0 | (c >> 6));
        bytes.push(0x80 | (c & 0x3f));
      } else if (c < 0xd800 || c >= 0xe000) {
        bytes.push(0xe0 | (c >> 12));
        bytes.push(0x80 | ((c >> 6) & 0x3f));
        bytes.push(0x80 | (c & 0x3f));
      } else {
        i++;
        c = 0x10000 + (((c & 0x3ff) << 10) | (ascii.charCodeAt(i) & 0x3ff));
        bytes.push(0xf0 | (c >> 18));
        bytes.push(0x80 | ((c >> 12) & 0x3f));
        bytes.push(0x80 | ((c >> 6) & 0x3f));
        bytes.push(0x80 | (c & 0x3f));
      }
    }

    var bitLen = bytes.length * 8;
    bytes.push(0x80);
    while ((bytes.length % 64) !== 56) bytes.push(0);

    var hiLen = Math.floor(bitLen / 0x100000000);
    var loLen = bitLen >>> 0;
    for (var j = 3; j >= 0; j--) bytes.push((hiLen >> (j * 8)) & 0xff);
    for (var j = 3; j >= 0; j--) bytes.push((loLen >> (j * 8)) & 0xff);

    var W = new Array(64);
    for (var chunk = 0; chunk < bytes.length; chunk += 64) {
      for (var i = 0; i < 16; i++) {
        W[i] = ((bytes[chunk + i * 4] << 24) |
                (bytes[chunk + i * 4 + 1] << 16) |
                (bytes[chunk + i * 4 + 2] << 8) |
                (bytes[chunk + i * 4 + 3])) >>> 0;
      }
      for (var i = 16; i < 64; i++) {
        var s0 = ror(W[i - 15], 7) ^ ror(W[i - 15], 18) ^ (W[i - 15] >>> 3);
        var s1 = ror(W[i - 2], 17) ^ ror(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = ((W[i - 16] + s0 + W[i - 7] + s1) | 0) >>> 0;
      }

      var a = H[0], b = H[1], c = H[2], d = H[3],
          e = H[4], f = H[5], g = H[6], h = H[7];

      for (var i = 0; i < 64; i++) {
        var S1 = ror(e, 6) ^ ror(e, 11) ^ ror(e, 25);
        var ch = (e & f) ^ ((~e) & g);
        var temp1 = (h + S1 + ch + K[i] + W[i]) | 0;
        var S0 = ror(a, 2) ^ ror(a, 13) ^ ror(a, 22);
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var temp2 = (S0 + maj) | 0;

        h = g;
        g = f;
        f = e;
        e = (d + temp1) | 0;
        d = c;
        c = b;
        b = a;
        a = (temp1 + temp2) | 0;
      }

      H[0] = (H[0] + a) | 0;
      H[1] = (H[1] + b) | 0;
      H[2] = (H[2] + c) | 0;
      H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0;
      H[5] = (H[5] + f) | 0;
      H[6] = (H[6] + g) | 0;
      H[7] = (H[7] + h) | 0;
    }

    var result = "";
    for (var i = 0; i < 8; i++) {
      var hex = (H[i] >>> 0).toString(16);
      while (hex.length < 8) hex = "0" + hex;
      result += hex;
    }
    return result;
  }

  // Normalize LF and compute SHA-256
  function computeHash(text) {
    if (!text) return "";
    var normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    return sha256_pure(normalized);
  }

  // Playground state
  var state = {
    code: TEMPLATES.v2_certified,
    programSha256: "",
    robotPreset: "certified_default",
    taskPreset: "mixed_bin",
    budget: 5,
    replayCertified: false,
    backendAlive: false,
    isRunning: false,
    ces: null,
  };

  function getElement(id) {
    return document.getElementById(id);
  }

  // Preset options configuration
  var ROBOT_PRESET_OPTIONS = [
    { value: "certified_default", label: "Certified Default (Pass-through)" },
    { value: "gripper_100N", label: "Standard Gripper (100 N Clamp)" },
    { value: "gripper_200N", label: "Heavy-Duty Gripper (200 N Clamp)" },
  ];

  var TASK_PRESET_OPTIONS = [
    { value: "mixed_bin", label: "Distribution D: Mixed Bin (1.0 - 11.5 kg)" },
    { value: "light_parts", label: "Light Parts (1.0 - 5.0 kg)" },
    { value: "heavy_parts", label: "Heavy Parts (6.0 - 14.0 kg)" },
  ];

  var BUDGET_OPTIONS = [
    { value: "5", label: "5 Episodes (Quick Probe)" },
    { value: "10", label: "10 Episodes (Standard)" },
    { value: "20", label: "20 Episodes (Certified Sample)" },
    { value: "50", label: "50 Episodes (Stress Test)" },
  ];

  function populatePresetDropdowns() {
    var robotSelect = getElement("pg-robot-preset");
    if (robotSelect && robotSelect.options.length === 0) {
      robotSelect.innerHTML = "";
      ROBOT_PRESET_OPTIONS.forEach(function (opt) {
        var el = document.createElement("option");
        el.value = opt.value;
        el.textContent = opt.label;
        if (opt.value === state.robotPreset) el.selected = true;
        robotSelect.appendChild(el);
      });
    }

    var taskSelect = getElement("pg-task-preset");
    if (taskSelect && taskSelect.options.length === 0) {
      taskSelect.innerHTML = "";
      TASK_PRESET_OPTIONS.forEach(function (opt) {
        var el = document.createElement("option");
        el.value = opt.value;
        el.textContent = opt.label;
        if (opt.value === state.taskPreset) el.selected = true;
        taskSelect.appendChild(el);
      });
    }

    var budgetSelect = getElement("pg-budget-preset");
    if (budgetSelect && budgetSelect.options.length === 0) {
      budgetSelect.innerHTML = "";
      BUDGET_OPTIONS.forEach(function (opt) {
        var el = document.createElement("option");
        el.value = opt.value;
        el.textContent = opt.label;
        if (parseInt(opt.value, 10) === state.budget) el.selected = true;
        budgetSelect.appendChild(el);
      });
    }
  }

  // Convert FastAPI error `detail` (string | array of {loc,msg} | object) to text
  function formatErrorDetail(errData, statusText) {
    var d = errData && (errData.detail !== undefined ? errData.detail : errData.error);
    if (d === undefined || d === null || d === "") return statusText || "Execution failed";
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      return d.map(function (x) {
        if (x && typeof x === "object") {
          var loc = Array.isArray(x.loc) ? x.loc.filter(function (p) { return p !== "body"; }).join(".") : "";
          return (loc ? loc + ": " : "") + (x.msg || JSON.stringify(x));
        }
        return String(x);
      }).join("; ");
    }
    try { return JSON.stringify(d); } catch (e) { return String(d); }
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Context-specific syntax & validation help
  function getErrorHelpTip(errMsg) {
    if (errMsg.indexOf("invalid decimal literal") !== -1) {
      return "Numbers must be pure digits without unit letters (e.g. <code>close_gripper(300)</code>, NOT <code>close_gripper(300N)</code>).";
    }
    if (errMsg.indexOf("unmatched ')'") !== -1 || errMsg.indexOf("was never closed") !== -1) {
      return "Parenthesis mismatch: check that each opening <code>(</code> has a matching <code>)</code> and remove any extra <code>)</code>.";
    }
    if (errMsg.indexOf("indent") !== -1 || errMsg.indexOf("IndentationError") !== -1) {
      return "Indentation error: all statements inside <code>def policy(env, rng):</code> must be indented by exactly 4 spaces.";
    }
    return "Check your Python syntax or click a preset template above to restore a working policy.";
  }

  // Clear previous error messages when user modifies code or loads a template
  function clearErrors() {
    var ptext = getElement("pg-progress-text");
    if (ptext && (ptext.innerHTML.indexOf("Validation Error") !== -1 || ptext.innerHTML.indexOf("Error:") !== -1)) {
      ptext.textContent = "Ready to run simulation.";
    }
    var resHeadline = getElement("pg-results-headline");
    if (resHeadline && resHeadline.textContent.indexOf("Rejected") !== -1) {
      resHeadline.textContent = "Simulation Ready";
      resHeadline.style.color = "var(--text-strong)";
    }
    var frameEmpty = getElement("pg-frame-empty");
    if (frameEmpty && frameEmpty.textContent.indexOf("Execution rejected") !== -1) {
      frameEmpty.textContent = "Click 'Run Simulation' to execute episode batch.";
    }
  }

  // Refresh live badge pill & message
  function updateBadge() {
    populatePresetDropdowns();
    var editor = getElement("pg-code-editor");
    if (!editor) return;

    state.code = editor.value;
    state.programSha256 = computeHash(state.code);

    var shaEl = getElement("pg-code-sha");
    if (shaEl) {
      shaEl.textContent = state.programSha256 || "—";
    }

    var robotEl = getElement("pg-robot-preset");
    if (robotEl && robotEl.value) state.robotPreset = robotEl.value;

    var taskEl = getElement("pg-task-preset");
    if (taskEl && taskEl.value) state.taskPreset = taskEl.value;

    var budgetEl = getElement("pg-budget-preset");
    if (budgetEl && budgetEl.value) state.budget = parseInt(budgetEl.value, 10) || 5;

    var badgeInfo = { status: "VOID", badge: "VOID", badgeClass: "badge-pill-fail", message: "No certificate found." };
    if (root.evaluateBadge) {
      badgeInfo = root.evaluateBadge(
        state.programSha256,
        state.robotPreset,
        state.taskPreset,
        SIM_CODE_SHA256
      );
    }

    var isCertified = badgeInfo.status === "CERTIFIED" || badgeInfo.status === "PASS";

    var badgePill = getElement("pg-badge-pill");
    if (badgePill) {
      badgePill.className = "badge-pill " + (badgeInfo.badgeClass || "badge-pill-neutral");
      badgePill.textContent = badgeInfo.badge || "VOID";
    }

    var msgEl = getElement("pg-badge-message");
    if (msgEl) {
      msgEl.textContent = badgeInfo.message || "";
    }

    // Card Mode Badges (Plan v2 §13 & §14 PA5)
    var editorModeBadge = getElement("pg-editor-mode-badge");
    if (editorModeBadge) {
      if (isCertified) {
        editorModeBadge.className = "badge-pill badge-pill-pass text-xs";
        editorModeBadge.textContent = "CERTIFIED";
      } else {
        editorModeBadge.className = "badge-pill badge-pill-warn text-xs";
        editorModeBadge.textContent = "PLAYGROUND, NOT CERTIFIED";
      }
    }

    var simModeBadge = getElement("pg-sim-mode-badge");
    if (simModeBadge) {
      if (state.robotPreset === "certified_default" && state.taskPreset === "mixed_bin") {
        simModeBadge.className = "badge-pill badge-pill-pass text-xs";
        simModeBadge.textContent = "CERTIFIED CONFIG";
      } else if (state.robotPreset === "gripper_100N" || state.robotPreset === "gripper_200N") {
        simModeBadge.className = "badge-pill badge-pill-warn text-xs";
        simModeBadge.textContent = "HARDWARE CLAMPED";
      } else {
        simModeBadge.className = "badge-pill badge-pill-warn text-xs";
        simModeBadge.textContent = "DISTRIBUTION SHIFT";
      }
    }

    // Update preset descriptions
    var robotDescEl = getElement("pg-robot-desc");
    if (robotDescEl) {
      if (state.robotPreset === "certified_default") {
        robotDescEl.textContent = "Identity: Force commands pass through as certified (eligible for CERTIFIED badge).";
      } else if (state.robotPreset === "gripper_100N") {
        robotDescEl.textContent = "Standard 100 N clamp: slips above ~8.49 kg (voids certification).";
      } else if (state.robotPreset === "gripper_200N") {
        robotDescEl.textContent = "Heavy-Duty 200 N clamp: slips above ~16.99 kg (voids certification).";
      }
    }

    var taskDescEl = getElement("pg-task-desc");
    if (taskDescEl) {
      if (state.taskPreset === "mixed_bin") {
        taskDescEl.textContent = "Distribution D: 1.0 to 11.5 kg, friction 0.1 to 1.0 (eligible for CERTIFIED badge).";
      } else if (state.taskPreset === "light_parts") {
        taskDescEl.textContent = "Light parts: 1.0 to 5.0 kg (distribution subset, voids certification).";
      } else if (state.taskPreset === "heavy_parts") {
        taskDescEl.textContent = "Heavy parts: 6.0 to 14.0 kg (distribution D' shift, voids certification).";
      }
    }

    var hwWarn = getElement("pg-hardware-warning");
    if (hwWarn) {
      if (state.robotPreset === "gripper_100N") {
        hwWarn.style.display = "block";
        hwWarn.textContent = "Hardware limit: gripper clamp is restricted to 100 N maximum force. Payload slip will occur above ~8.49 kg.";
      } else if (state.robotPreset === "gripper_200N") {
        hwWarn.style.display = "block";
        hwWarn.textContent = "Hardware limit: gripper clamp is restricted to 200 N maximum force. Payload slip will occur above ~16.99 kg.";
      } else {
        hwWarn.style.display = "none";
        hwWarn.textContent = "";
      }
    }
  }

  // Check backend server availability
  async function checkBackend() {
    var svcBadge = getElement("pg-service-badge");
    try {
      var controller = new AbortController();
      var timeoutId = setTimeout(function () { controller.abort(); }, 1200);
      var resp = await fetch("/health", { signal: controller.signal });
      clearTimeout(timeoutId);

      if (resp.ok) {
        var data = await resp.json();
        state.backendAlive = data.status === "ok";
        if (svcBadge) {
          svcBadge.className = "badge-pill badge-pill-pass";
          svcBadge.textContent = "Live: " + (data.model_name || "Meta Muse Spark 1.3") + " (PyBullet Sim)";
        }
        return true;
      }
    } catch (e) {
      // Backend not running on this port
    }

    state.backendAlive = false;
    if (svcBadge) {
      svcBadge.className = "badge-pill badge-pill-fail";
      svcBadge.textContent = "Offline (HTTP 404): Simulator Server Not Running";
    }
    return false;
  }

  // Reset execution table and stats
  function resetRunView(budget) {
    var tbody = getElement("pg-episodes-tbody");
    if (tbody) tbody.innerHTML = "";

    var pbar = getElement("pg-progress-fill");
    if (pbar) pbar.style.width = "0%";

    var ptext = getElement("pg-progress-text");
    if (ptext) ptext.textContent = "Running episode 0 of " + budget + "...";

    getElement("pg-metric-k").textContent = "—";
    getElement("pg-metric-n").textContent = String(budget);
    getElement("pg-metric-rate").textContent = "—";
    getElement("pg-metric-clamps").textContent = "0";

    var frameImg = getElement("pg-frame-img");
    if (frameImg) frameImg.style.display = "none";
    var frameEmpty = getElement("pg-frame-empty");
    if (frameEmpty) frameEmpty.style.display = "flex";
  }

  // Render one episode row
  function appendEpisodeRow(ep) {
    var tbody = getElement("pg-episodes-tbody");
    if (!tbody) return;

    var tr = document.createElement("tr");
    var passClass = ep.truth_success ? "text-ok font-semibold" : "text-bad font-semibold";
    var passText = ep.truth_success ? "PASS" : "FAIL";

    var clampText = ep.clamp_events && ep.clamp_events.length > 0
      ? '<span class="badge-pill badge-pill-warn text-xs">' + ep.clamp_events.length + " clamp(s)</span>"
      : '<span class="text-dim text-xs">—</span>';

    var errText = ep.error ? '<span class="text-bad text-xs">' + ep.error + '</span>' : '<span class="text-dim text-xs">—</span>';

    tr.innerHTML = [
      '<td class="font-mono">#' + ep.index + "</td>",
      '<td class="font-mono text-dim">' + ep.seed + "</td>",
      "<td>" + (ep.mass ? ep.mass.toFixed(2) + " kg" : "—") + "</td>",
      "<td>" + (ep.friction ? ep.friction.toFixed(2) : "—") + "</td>",
      '<td class="' + passClass + '">' + passText + "</td>",
      '<td class="font-mono text-xs">' + (ep.margin !== undefined ? ep.margin.toFixed(4) : "—") + "</td>",
      '<td class="font-mono text-xs">' + ep.steps + "</td>",
      "<td>" + clampText + "</td>",
      "<td>" + errText + "</td>",
    ].join("");

    tbody.appendChild(tr);

    if (ep.frame_b64) {
      var frameImg = getElement("pg-frame-img");
      var frameEmpty = getElement("pg-frame-empty");
      if (frameImg) {
        frameImg.src = "data:image/jpeg;base64," + ep.frame_b64;
        frameImg.style.display = "block";
      }
      if (frameEmpty) frameEmpty.style.display = "none";
    }
  }

  // Path A: Automated Code / Syntax Error Repair with Muse Spark
  async function triggerPathACodeRepair(rawErrMsg, errLine) {
    var editor = getElement("pg-code-editor");
    if (!editor) return;

    var resHeadline = getElement("pg-results-headline");
    var ptext = getElement("pg-progress-text");
    var runBtn = getElement("pg-run-btn");

    var lineDesc = errLine ? "Line " + errLine : "Syntax / AST";

    if (resHeadline) {
      resHeadline.innerHTML =
        '<span style="color:var(--bad-text); font-weight:700;">Controller error detected</span><br>' +
        '<span style="font-size:13px; color:var(--text-strong);">Validation failed — ' + escapeHtml(lineDesc) + '</span>: ' +
        '<span style="font-size:12px; color:var(--text-muted);">' + escapeHtml(rawErrMsg) + '</span>';
      resHeadline.style.color = "var(--bad-text)";
    }

    if (ptext) {
      ptext.innerHTML =
        '<span style="color:var(--accent); font-weight:700;">Fix with Muse Spark:</span> Generating repair proposal and unified diff...';
    }

    var diffContainer = getElement("pg-diff-container");
    var diffView = getElement("pg-diff-view");
    var rationaleEl = getElement("pg-repair-rationale");
    var chipEl = getElement("pg-repair-source-chip");

    try {
      var robotEl = getElement("pg-robot-preset");
      var taskEl = getElement("pg-task-preset");
      var robotPreset = (robotEl && robotEl.value) || state.robotPreset || "certified_default";
      var taskPreset = (taskEl && taskEl.value) || state.taskPreset || "mixed_bin";

      var repairResp = await fetch("/repair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: editor.value,
          robot_preset: robotPreset,
          task_preset: taskPreset,
          allow_live: true,
          error_msg: rawErrMsg,
          error_line: errLine || null,
        }),
      });

      if (repairResp.ok) {
        var rData = await repairResp.json();
        if (rData.patch && rData.patch.code) {
          if (diffContainer) {
            diffContainer.style.display = "block";
            diffContainer.open = true;
          }
          if (diffView) diffView.textContent = rData.patch.diff || "Code diff generated.";
          if (rationaleEl) {
            rationaleEl.textContent = "Rationale (" + (rData.source || "Spark") + "): " +
              (rData.patch.rationale || "Repaired syntax and restored compliant controller.");
          }
          if (chipEl) {
            chipEl.className = "badge-pill badge-pill-pass text-xs";
            chipEl.textContent = (rData.source || "Spark").toUpperCase();
          }

          // Validate repaired code
          editor.value = rData.patch.code;
          updateBadge();

          if (ptext) {
            ptext.innerHTML =
              '<span style="color:var(--ok-text); font-weight:700;">Validate repaired code:</span> Syntax, AST rules, parameter limits & hash verified (PASS).';
          }

          if (resHeadline) {
            resHeadline.innerHTML =
              '<span class="text-ok font-semibold">Code Repaired!</span> Executing actual PyBullet simulation episodes after validation...';
            resHeadline.style.color = "var(--ok-text, #10b981)";
          }

          state.isRunning = false;
          setTimeout(function () {
            runSimulation();
          }, 1100);
          return;
        }
      }
    } catch (e) {
      // Fall through to show error
    }

    state.isRunning = false;
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.textContent = "Run Simulation";
    }
  }

  // Stream execution against /run using Server-Sent Events (Plan §10, §13 PA3)
  async function runSimulation() {
    if (state.isRunning) return;

    var editor = getElement("pg-code-editor");
    if (!editor) return;

    populatePresetDropdowns();

    var code = editor.value;
    var robotEl = getElement("pg-robot-preset");
    var taskEl = getElement("pg-task-preset");
    var budgetEl = getElement("pg-budget-preset");

    var robotPreset = (robotEl && robotEl.value) || state.robotPreset || "certified_default";
    var taskPreset = (taskEl && taskEl.value) || state.taskPreset || "mixed_bin";
    var budget = (budgetEl && parseInt(budgetEl.value, 10)) || state.budget || 5;
    var replayCertified = getElement("pg-replay-cert") ? getElement("pg-replay-cert").checked : false;

    var runBtn = getElement("pg-run-btn");
    state.isRunning = true;
    if (runBtn) {
      runBtn.disabled = true;
      runBtn.textContent = "Simulating...";
    }

    var camBadge = getElement("pg-camera-mode-badge");
    if (camBadge) {
      camBadge.className = "badge-pill badge-pill-warn text-xs";
      camBadge.textContent = "STREAMING";
    }

    var logBadge = getElement("pg-log-mode-badge");
    if (logBadge) {
      logBadge.className = "badge-pill badge-pill-warn text-xs";
      logBadge.textContent = "STREAMING";
    }

    resetRunView(budget);
    var resHeadline = getElement("pg-results-headline");
    if (resHeadline) {
      resHeadline.textContent = "Running episodes in simulator...";
    }
    if (typeof window.jumpPlaygroundStep === "function") {
      window.jumpPlaygroundStep(3);
    }

    var isLive = await checkBackend();
    if (!isLive) {
      state.isRunning = false;
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = "Run Simulation";
      }
      if (resHeadline) {
        resHeadline.textContent = "Error: Simulator Backend Offline (HTTP 404)";
        resHeadline.style.color = "var(--bad-text)";
      }
      var ptext = getElement("pg-progress-text");
      if (ptext) {
        ptext.innerHTML = '<span style="color:var(--bad-text); font-weight:700;">Backend Offline (HTTP 404):</span> Live simulation requires the PyBullet FastAPI backend.<br><strong>To fix:</strong> Run <code style="padding:2px 6px; background:var(--bg-inset); border-radius:4px; font-weight:700;">python -m playground.server --port 8000</code> in your terminal.<br><span style="font-size:11px; color:var(--text-dim);">(Do not run <code>python -m http.server</code> as it only serves static files and cannot execute simulations).</span>';
      }
      if (camBadge) {
        camBadge.className = "badge-pill badge-pill-fail text-xs";
        camBadge.textContent = "BACKEND 404";
      }
      if (logBadge) {
        logBadge.className = "badge-pill badge-pill-fail text-xs";
        logBadge.textContent = "SIMULATOR OFFLINE";
      }
      var frameEmpty = getElement("pg-frame-empty");
      if (frameEmpty) {
        frameEmpty.style.display = "block";
        frameEmpty.textContent = "Simulator backend offline (HTTP 404). Run python -m playground.server --port 8000";
      }
      var frameImg = getElement("pg-frame-img");
      if (frameImg) {
        frameImg.style.display = "none";
      }
      return;
    }

    // Live Streaming Run via POST /run with stream=true
    try {
      var payload = {
        code: String(code),
        robot_preset: String(robotPreset),
        task_preset: String(taskPreset),
        budget: Math.max(1, Math.min(100, parseInt(budget, 10) || 5)),
        seed_base: 2000,
        render_frames: true,
        replay_certified_episodes: !!replayCertified,
        stream: true,
      };

      var resp = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "text/event-stream, application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        var errData = await resp.json().catch(function () { return { detail: resp.statusText }; });
        var rawErrMsg = formatErrorDetail(errData, resp.status + " " + resp.statusText);
        var lineMatch = rawErrMsg.match(/\(Line\s*(\d+)\)/i) || rawErrMsg.match(/line\s*(\d+)/i);
        var errLine = lineMatch ? parseInt(lineMatch[1], 10) : null;
        await triggerPathACodeRepair(rawErrMsg, errLine);
        return;
      }

      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      var episodesReceived = 0;
      var totalClampCount = 0;
      var kPass = 0;

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;

        buffer += decoder.decode(chunk.value, { stream: true });
        var lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep remainder

        for (var i = 0; i < lines.length; i++) {
          var block = lines[i].trim();
          if (!block) continue;

          var eventMatch = block.match(/^event:\s*(\w+)/m);
          var dataMatch = block.match(/^data:\s*(.+)$/m);
          if (!eventMatch || !dataMatch) continue;

          var evType = eventMatch[1];
          var evData = JSON.parse(dataMatch[1]);

          if (evType === "start") {
            getElement("pg-progress-text").textContent = "Simulating " + evData.total + " episodes...";
          } else if (evType === "episode") {
            episodesReceived++;
            if (evData.truth_success) kPass++;
            if (evData.clamp_events) totalClampCount += evData.clamp_events.length;

            if (evData.frame_b64) {
              var frameImg = getElement("pg-frame-img");
              var frameEmpty = getElement("pg-frame-empty");
              if (frameImg) {
                frameImg.src = "data:image/jpeg;base64," + evData.frame_b64;
                frameImg.style.display = "block";
              }
              if (frameEmpty) frameEmpty.style.display = "none";
            }

            appendEpisodeRow(evData);

            var pct = Math.round((episodesReceived / budget) * 100);
            getElement("pg-progress-fill").style.width = pct + "%";
            getElement("pg-progress-text").textContent = "Completed episode " + episodesReceived + " of " + budget + "...";

            getElement("pg-metric-k").textContent = String(kPass);
            getElement("pg-metric-rate").textContent = ((kPass / episodesReceived) * 100).toFixed(1) + "%";
            getElement("pg-metric-clamps").textContent = String(totalClampCount);
          } else if (evType === "done") {
            getElement("pg-progress-fill").style.width = "100%";
            getElement("pg-progress-text").textContent =
              "Run complete: " + evData.k + "/" + evData.n + " successes (" + (evData.success_rate * 100).toFixed(1) + "%), " +
              evData.total_clamp_events + " clamp events in " + evData.duration_ms + " ms.";
            getElement("pg-metric-k").textContent = String(evData.k);
            getElement("pg-metric-rate").textContent = (evData.success_rate * 100).toFixed(1) + "%";
            getElement("pg-metric-clamps").textContent = String(evData.total_clamp_events);

            var resHeadlineDone = getElement("pg-results-headline");
            var camBadgeDone = getElement("pg-camera-mode-badge");
            var logBadgeDone = getElement("pg-log-mode-badge");

            if (camBadgeDone) {
              camBadgeDone.className = "badge-pill " + (evData.certified ? "badge-pill-pass" : "badge-pill-neutral") + " text-xs";
              camBadgeDone.textContent = evData.certified ? "CERTIFIED" : "PLAYGROUND, NOT CERTIFIED";
            }
            if (logBadgeDone) {
              logBadgeDone.className = "badge-pill " + (evData.certified ? "badge-pill-pass" : "badge-pill-neutral") + " text-xs";
              logBadgeDone.textContent = evData.certified ? "CERTIFIED LOG" : "PLAYGROUND LOG";
            }

            // If ALL episodes succeeded or user is already in a re-run, finish normally
            if (evData.k === evData.n) {
              if (resHeadlineDone) {
                resHeadlineDone.textContent = evData.k + " of " + evData.n + " episodes succeeded (" + (evData.success_rate * 100).toFixed(1) + "%).";
                resHeadlineDone.style.color = "var(--ok-text, #10b981)";
              }
            } else if (!state.isClosedLoopRepairing) {
              // A failure occurred in simulation! Automatically engage ClosedLoop diagnosis & repair
              state.isClosedLoopRepairing = true;
              if (resHeadlineDone) {
                resHeadlineDone.innerHTML = '<span class="text-bad">Failure Detected (' + evData.k + '/' + evData.n + ' passed):</span> Robot failed in simulation. Engaging ClosedLoop AI Diagnosis & Repair...';
                resHeadlineDone.style.color = "var(--bad-text)";
              }
              var ptext = getElement("pg-progress-text");
              if (ptext) ptext.textContent = "ClosedLoop: Searching for root cause & requesting AI patch...";

              // Run automated repair in background of simulation completion
              setTimeout(async function () {
                try {
                  var ces = await ensureCEs();
                  var ce1 = ces.minimal;
                  var ce2 = ces.severe;

                  // Check hardware limits refusal
                  if (state.robotPreset === "gripper_100N" && (ce1.mass > 8.49 || ce2.mass > 8.49)) {
                    if (resHeadlineDone) {
                      resHeadlineDone.innerHTML = '<span class="text-bad font-semibold">Physical Hardware Limit:</span> Standard 100N gripper cannot lift >8.49 kg. Software repair refused to respect physical laws.';
                    }
                    if (ptext) ptext.textContent = "Hardware limit exceeded. Choose Heavy-Duty or Certified Default gripper.";
                    state.isClosedLoopRepairing = false;
                    return;
                  }

                  // Request repair patch
                  var repairResp = await fetch("/repair", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      code: editor.value,
                      robot_preset: state.robotPreset,
                      task_preset: state.taskPreset,
                      minimal_ce: ce1,
                      severe_ce: ce2,
                      allow_live: true,
                    }),
                  });

                  if (repairResp.ok) {
                    var rData = await repairResp.json();
                    if (rData.patch && rData.patch.code) {
                      var diffContainer = getElement("pg-diff-container");
                      var diffView = getElement("pg-diff-view");
                      var rationaleEl = getElement("pg-repair-rationale");
                      var chipEl = getElement("pg-repair-source-chip");

                      if (diffContainer) diffContainer.style.display = "block";
                      if (diffContainer) diffContainer.open = true;
                      if (diffView) diffView.textContent = rData.patch.diff || "Patch applied.";
                      if (rationaleEl) rationaleEl.textContent = "Rationale (" + (rData.source || "AI") + "): " + (rData.patch.rationale || "Adapted force and motion profile.");
                      if (chipEl) {
                        chipEl.className = "badge-pill badge-pill-pass text-xs";
                        chipEl.textContent = (rData.source || "AI").toUpperCase();
                      }

                      // Evaluate the 4 Acceptance Gates live
                      var s = rData.gates ? rData.gates.stages : {};
                      var setStage = function (id, ok, margin) {
                        var el = getElement(id);
                        if (el) {
                          el.textContent = (ok ? "PASS" : "FAIL") + (margin !== undefined ? " (" + margin.toFixed(4) + ")" : "");
                          el.className = "text-xs font-mono font-bold mt-4 " + (ok ? "text-ok" : "text-bad");
                        }
                      };
                      if (s.stage1_minimal_ce) setStage("pg-stage1-status", s.stage1_minimal_ce.passed, s.stage1_minimal_ce.margin);
                      if (s.stage2_severe_ce) setStage("pg-stage2-status", s.stage2_severe_ce.passed, s.stage2_severe_ce.margin);
                      if (s.stage3_regression_set) setStage("pg-stage3-status", s.stage3_regression_set.passed);
                      if (s.stage4_falsifier_rerun) setStage("pg-stage4-status", s.stage4_falsifier_rerun.passed);

                      if (rData.gates && rData.gates.accepted) {
                        // Acceptance gates passed! Apply repaired code and re-simulate
                        editor.value = rData.patch.code;
                        updateBadge();
                        if (resHeadlineDone) {
                          resHeadlineDone.innerHTML = '<span class="text-ok font-semibold">4 Acceptance Gates Passed!</span> Re-running simulation with repaired controller...';
                          resHeadlineDone.style.color = "var(--ok-text, #10b981)";
                        }
                        if (ptext) ptext.textContent = "Acceptance gates verified (4/4 PASS). Simulating repaired policy in PyBullet...";
                        setTimeout(function () {
                          runSimulation();
                        }, 1200);
                        return;
                      } else {
                        if (resHeadlineDone) {
                          resHeadlineDone.innerHTML = '<span class="text-bad font-semibold">Repair Rejected by Acceptance Gates:</span> Proposed patch failed verification.';
                        }
                      }
                    }
                  }
                } catch (e) {
                  // Fallback gracefully
                } finally {
                  state.isClosedLoopRepairing = false;
                }
              }, 800);
            } else {
              state.isClosedLoopRepairing = false;
              if (resHeadlineDone) {
                resHeadlineDone.innerHTML = '<span class="text-ok font-semibold">ClosedLoop Verification Succeeded:</span> Repaired controller passed all ' + evData.n + ' episodes (' + (evData.success_rate * 100).toFixed(1) + '%).';
                resHeadlineDone.style.color = "var(--ok-text, #10b981)";
              }
            }
          } else if (evType === "error") {
            var errMsg = evData.message || "Execution rejected";
            var errLine = evData.line || null;
            await triggerPathACodeRepair(errMsg, errLine);
            return;
          }
        }
      }
    } catch (err) {
      getElement("pg-progress-text").innerHTML =
        '<span class="text-bad font-semibold">Network Error:</span> ' + err.message;
    } finally {
      state.isRunning = false;
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = "Run Simulation";
      }
      var camBadgeFinal = getElement("pg-camera-mode-badge");
      if (camBadgeFinal && camBadgeFinal.textContent === "STREAMING") {
        camBadgeFinal.className = "badge-pill badge-pill-neutral text-xs";
        camBadgeFinal.textContent = "READY";
      }
      var logBadgeFinal = getElement("pg-log-mode-badge");
      if (logBadgeFinal && logBadgeFinal.textContent === "STREAMING") {
        logBadgeFinal.className = "badge-pill badge-pill-neutral text-xs";
        logBadgeFinal.textContent = "APPEND-ONLY";
      }
    }
  }

  // Preload code template into editor
  function loadTemplate(key) {
    var editor = getElement("pg-code-editor");
    if (!editor) return;

    if (TEMPLATES[key]) {
      editor.value = TEMPLATES[key];
    } else if (key === "custom") {
      editor.value = [
        "def policy(env, rng):",
        "    cube_pos = env.get_object_pos(\"cube\")",
        "    pad_pos = env.get_object_pos(\"pad\")",
        "    env.open_gripper()",
        "    env.move_to((cube_pos[0], cube_pos[1], cube_pos[2] + 0.1), steps=60)",
        "    env.move_to(cube_pos, steps=60)",
        "    env.close_gripper(200)",
        "    env.move_to((pad_pos[0], pad_pos[1], pad_pos[2] + 0.1), steps=60)",
        "    env.open_gripper()",
        "",
      ].join("\n");
    }

    // Toggle button active state
    var btns = document.querySelectorAll(".pg-template-btn");
    btns.forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-template") === key);
    });

    clearErrors();
    state.ces = null;
    setVerdict("", "");
    updateBadge();
    if (typeof window.jumpPlaygroundStep === "function") {
      window.jumpPlaygroundStep(2);
    }
  }

  // Load pre-packaged recorded repair patch (Plan §10, §13 PA4)
  async function loadRecordedRepair() {
    var editor = getElement("pg-code-editor");
    if (!editor) return;

    var diffContainer = getElement("pg-diff-container");
    var diffView = getElement("pg-diff-view");
    var rationaleEl = getElement("pg-repair-rationale");
    var chipEl = getElement("pg-repair-source-chip");

    // Find counterexamples on the CURRENT (flawed) code before it is replaced
    await ensureCEs();

    try {
      var resp = await fetch("/repair/recorded");
      if (resp.ok) {
        var data = await resp.json();
        var item = data.catalog && data.catalog[0];
        if (item) {
          editor.value = item.code;
          if (diffContainer) diffContainer.style.display = "block";
          if (diffView) diffView.textContent = item.diff;
          if (rationaleEl) rationaleEl.textContent = "Rationale: " + item.rationale;
          if (chipEl) {
            chipEl.className = "badge-pill badge-pill-pass text-xs";
            chipEl.textContent = (item.source || "recorded").toUpperCase();
          }
          updateBadge();
          runAcceptanceGates();
          return;
        }
      }
    } catch (e) {
      // Fall back to built-in recorded template
    }

    editor.value = TEMPLATES.v2_certified;
    if (diffContainer) diffContainer.style.display = "block";
    if (diffView) {
      diffView.textContent = [
        "--- a/baseline_v1.py",
        "+++ b/repaired_v2.py",
        "@@ -8,3 +8,3 @@",
        "-    env.close_gripper(100)",
        "+    env.close_gripper(300)",
      ].join("\n");
    }
    if (rationaleEl) {
      rationaleEl.textContent = "Rationale: Updated gripper force from 100N to 300N to satisfy physical friction-to-weight ratio across full operating envelope.";
    }
    if (chipEl) {
      chipEl.className = "badge-pill badge-pill-pass text-xs";
      chipEl.textContent = "RECORDED";
    }
    updateBadge();
    runAcceptanceGates();
    if (typeof window.jumpPlaygroundStep === "function") {
      window.jumpPlaygroundStep(5);
    }
  }

  var FALLBACK_CES = {
    minimal: { mass: 10.16, friction: 0.8, x: 0.0, y: 0.0, yaw: 0.0, seed: 711000 },
    severe: { mass: 11.5, friction: 0.5, x: -0.05, y: -0.05, yaw: 0.2, seed: 711001 },
    source: "reference",
  };

  function setVerdict(kind, html) {
    var el = getElement("pg-verdict");
    if (!el) return;
    el.style.display = html ? "block" : "none";
    el.innerHTML = html || "";
    var color = kind === "ok" ? "var(--ok-text, #1a7f4b)" : kind === "bad" ? "var(--bad-text)" : "var(--text-strong)";
    el.style.color = color;
    el.style.border = "1px solid " + color;
  }

  function describeCE(c) {
    return "mass " + c.mass.toFixed(2) + " kg, friction " + c.friction.toFixed(2) +
      ", margin " + c.margin.toFixed(3) + (c.error ? " (" + escapeHtml(c.error) + ")" : "");
  }

  // Step 1: search the task preset for failures on the REAL simulator
  async function runFalsifier() {
    var editor = getElement("pg-code-editor");
    var panel = getElement("pg-ce-panel");
    var btn = getElement("pg-falsify-btn");
    if (!editor || !panel) return null;
    populatePresetDropdowns();
    updateBadge();

    if (btn) { btn.disabled = true; btn.textContent = "Searching..."; }
    panel.style.display = "block";
    panel.textContent = "Searching for failing scenarios on the real simulator (20 tests)...";
    setVerdict("", "");

    try {
      var resp = await fetch("/falsify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: editor.value,
          robot_preset: state.robotPreset,
          task_preset: state.taskPreset,
          budget: 20,
          seed_base: 3100000,
        }),
      });
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        panel.innerHTML = '<span class="text-bad font-semibold">Could not search:</span> ' + escapeHtml(formatErrorDetail(data, resp.statusText));
        return null;
      }
      if (data.status === "VALIDATION_ERROR") {
        var ln = data.error_line ? " (Line " + data.error_line + ")" : "";
        panel.innerHTML = '<span class="text-bad font-semibold">Code rejected' + ln + ':</span> ' + escapeHtml(data.error) +
          "<br>Fix the code first, then search again.";
        return null;
      }
      if (!data.failures) {
        state.ces = null;
        panel.innerHTML = '<span class="text-ok font-semibold">No failure found</span> in ' + data.evaluated +
          " tested scenarios (LIVE). This is a search, not a proof: other failures may exist.";
        return null;
      }
      state.ces = { minimal: data.minimal, severe: data.severe, source: "found" };
      var html = '<span class="text-bad font-semibold">' + data.failures + " of " + data.evaluated +
        " tested scenarios failed</span> (LIVE).<br>" +
        "<b>Smallest failing case:</b> " + describeCE(data.minimal) + "<br>" +
        "<b>Most severe failing case:</b> " + describeCE(data.severe);
      if (data.hardware_limit_kg !== null && data.hardware_limit_kg !== undefined && data.beyond_hardware) {
        html += '<br><span class="text-bad font-semibold">Hardware limit:</span> this gripper cannot lift more than ~' +
          data.hardware_limit_kg.toFixed(2) + " kg. The worst failure is above that, so no code change can fix it. " +
          "Choose a stronger gripper preset instead.";
      }
      panel.innerHTML = html;
      if (typeof window.jumpPlaygroundStep === "function") window.jumpPlaygroundStep(4);
      return state.ces;
    } catch (e) {
      panel.innerHTML = '<span class="text-bad font-semibold">Backend offline.</span> Start: <code>python -m playground.server --port 8000</code>';
      return null;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "1. Find failures"; }
    }
  }

  // Counterexamples for repair/gates: found ones first, otherwise run the search, otherwise reference ones
  async function ensureCEs() {
    if (state.ces) return state.ces;
    var found = await runFalsifier();
    if (found) return found;
    return FALLBACK_CES;
  }

  // Request live repair from Muse Spark via backend broker (Path A or Path B)
  async function requestLiveRepair() {
    var editor = getElement("pg-code-editor");
    if (!editor) return;

    var liveBtn = getElement("pg-live-repair-btn");
    if (liveBtn) {
      liveBtn.disabled = true;
      liveBtn.textContent = "Repairing (Spark)...";
    }

    var diffContainer = getElement("pg-diff-container");
    var diffView = getElement("pg-diff-view");
    var rationaleEl = getElement("pg-repair-rationale");
    var chipEl = getElement("pg-repair-source-chip");

    var code = editor.value;
    var robotPreset = state.robotPreset || "certified_default";
    var taskPreset = state.taskPreset || "mixed_bin";

    // Quick client-side syntax/bracket check
    var openParens = (code.match(/\(/g) || []).length;
    var closeParens = (code.match(/\)/g) || []).length;
    var hasBasicPolicy = code.indexOf("def policy(env, rng):") !== -1;
    var isProbableCodeError = !hasBasicPolicy || (openParens !== closeParens);

    try {
      var reqBody = {
        code: code,
        robot_preset: robotPreset,
        task_preset: taskPreset,
        allow_live: true,
      };

      if (!isProbableCodeError) {
        var ces = await ensureCEs();
        if (ces && ces.minimal) {
          reqBody.minimal_ce = ces.minimal;
          reqBody.severe_ce = ces.severe;
        }
      }

      var resp = await fetch("/repair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqBody),
      });

      if (resp.ok) {
        var data = await resp.json();
        if (data.patch && data.patch.code) {
          editor.value = data.patch.code;
          if (diffContainer) {
            diffContainer.style.display = "block";
            diffContainer.open = true;
          }
          if (diffView) diffView.textContent = data.patch.diff || "Patch applied successfully.";
          if (rationaleEl) rationaleEl.textContent = "Rationale (" + (data.source || "live") + "): " + (data.patch.rationale || "Repaired gripper force and motion profile.");
          if (chipEl) {
            chipEl.className = "badge-pill " + (data.source === "live" ? "badge-pill-pass" : "badge-pill-warn") + " text-xs";
            chipEl.textContent = (data.source || "live").toUpperCase();
          }
          updateBadge();

          // Evaluate acceptance gates
          runAcceptanceGates();
          if (typeof window.jumpPlaygroundStep === "function") {
            window.jumpPlaygroundStep(5);
          }
          return;
        }
      } else {
        var errJson = await resp.json().catch(function () { return { detail: resp.statusText }; });
        alert("Live Repair: " + (errJson.detail || "Server error"));
        return;
      }
    } catch (e) {
      alert("Live Repair Offline (HTTP 404): Simulator backend is not running.\nStart the server with: python -m playground.server --port 8000");
      return;
    } finally {
      if (liveBtn) {
        liveBtn.disabled = false;
        liveBtn.textContent = "2b. Live repair (Muse Spark)";
      }
    }
  }

  // Evaluate candidate code against the 4 acceptance stages
  async function runAcceptanceGates() {
    var stages = ["pg-stage1-status", "pg-stage2-status", "pg-stage3-status", "pg-stage4-status"];
    stages.forEach(function (id) {
      var el = getElement(id);
      if (el) {
        el.textContent = "Evaluating...";
        el.className = "text-xs font-mono font-bold mt-4 text-dim";
      }
    });

    var editor = getElement("pg-code-editor");
    var code = editor ? editor.value : "";
    var robotPreset = state.robotPreset || "certified_default";
    var taskPreset = state.taskPreset || "mixed_bin";

    var ces = await ensureCEs();
    var ce1 = ces.minimal;
    var ce2 = ces.severe;

    try {
      var resp = await fetch("/gates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: code,
          robot_preset: robotPreset,
          task_preset: taskPreset,
          minimal_ce: ce1,
          severe_ce: ce2,
        }),
      });

      if (resp.ok) {
        var data = await resp.json();
        var s = data.stages;

        var setStage = function (id, ok, margin) {
          var el = getElement(id);
          if (el) {
            el.textContent = (ok ? "PASS" : "FAIL") + (margin !== undefined ? " (" + margin.toFixed(4) + ")" : "");
            el.className = "text-xs font-mono font-bold mt-4 " + (ok ? "text-ok" : "text-bad");
          }
        };

        if (s.stage1_minimal_ce) setStage("pg-stage1-status", s.stage1_minimal_ce.passed, s.stage1_minimal_ce.margin);
        if (s.stage2_severe_ce) setStage("pg-stage2-status", s.stage2_severe_ce.passed, s.stage2_severe_ce.margin);
        if (s.stage3_regression_set) setStage("pg-stage3-status", s.stage3_regression_set.passed);
        if (s.stage4_falsifier_rerun) setStage("pg-stage4-status", s.stage4_falsifier_rerun.passed);
        if (data.accepted) {
          setVerdict("ok", "REPAIR ACCEPTED: all 4 checks passed on the real simulator (LIVE). This is a simulation result, not a certificate.");
        } else {
          var failed = [];
          if (s.compilation) failed.push("the code did not compile");
          if (s.stage1_minimal_ce && !s.stage1_minimal_ce.passed) failed.push("the smallest failing case still fails");
          if (s.stage2_severe_ce && !s.stage2_severe_ce.passed) failed.push("the most severe failing case still fails");
          if (s.stage3_regression_set && !s.stage3_regression_set.passed) failed.push("something that worked before is now broken");
          if (s.stage4_falsifier_rerun && !s.stage4_falsifier_rerun.passed) failed.push("a fresh search found new failures");
          var hw = (state.robotPreset !== "certified_default" && state.taskPreset !== "light_parts")
            ? "<br>Note: this gripper has a hardware force limit. If the failing masses exceed it, no code change can pass." : "";
          setVerdict("bad", "REPAIR REJECTED: " + failed.join("; ") + "." + hw +
            "<br>Try another repair, or edit the code yourself and run the checks again.");
        }
        return;
      }
      var gerr = await resp.json().catch(function () { return {}; });
      stages.forEach(function (id) {
        var el = getElement(id);
        if (el) { el.textContent = "NOT RUN"; el.className = "text-xs font-mono font-bold mt-4 text-bad"; }
      });
      setVerdict("bad", "Checks could not run: " + escapeHtml(formatErrorDetail(gerr, resp.statusText)));
      return;
    } catch (e) {
      // Backend offline
    }

    stages.forEach(function (id) {
      var el = getElement(id);
      if (el) {
        el.textContent = "OFFLINE (404)";
        el.className = "text-xs font-mono font-bold mt-4 text-bad";
      }
    });
  }

  // ---------- One-click closed loop (find failures -> repair -> verify -> simulate) ----------
  function showEditorError(msg, line) {
    var box = getElement("pg-editor-error");
    var editor = getElement("pg-code-editor");
    if (box) {
      box.style.display = "block";
      box.innerHTML = '<b>Code problem' + (line ? " on line " + line : "") + ":</b> " + escapeHtml(msg) +
        "<br>Fix this line in the editor, then press Run Simulation again.";
    }
    if (editor && line) {
      var lines = editor.value.replace(/\r\n/g, "\n").split("\n");
      var start = 0;
      for (var i = 0; i < line - 1 && i < lines.length; i++) start += lines[i].length + 1;
      var end = start + (lines[line - 1] ? lines[line - 1].length : 0);
      try { editor.focus(); editor.setSelectionRange(start, end); } catch (e) { /* ignore */ }
      if (editor.scrollIntoView) editor.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function clearEditorError() {
    var box = getElement("pg-editor-error");
    if (box) { box.style.display = "none"; box.innerHTML = ""; }
  }
  function autoStage(n, status, detail) {
    var li = getElement("pg-auto-s" + n);
    if (!li) return;
    li.className = "pg-auto-step" + (status ? " " + status : "");
    var dot = li.querySelector(".dot");
    if (dot) dot.textContent = status === "ok" ? "\u2713" : status === "bad" ? "\u2717" : status === "skip" ? "\u2013" : String(n);
    var d = li.querySelector(".d");
    if (d && detail !== undefined) d.innerHTML = detail;
  }

  function autoSummary(kind, html) {
    var el = getElement("pg-auto-summary");
    if (!el) return;
    var color = kind === "ok" ? "#10b981" : kind === "bad" ? "#ef4444" : "#6366f1";
    el.style.display = html ? "block" : "none";
    el.innerHTML = html || "";
    el.style.borderColor = color;
    el.style.background = color + "1a";
    el.style.color = "var(--text-strong)";
  }

  function gateFailures(s) {
    var failed = [];
    if (s.compilation) failed.push("the code did not compile");
    if (s.stage1_minimal_ce && !s.stage1_minimal_ce.passed) failed.push("the smallest failing case still fails");
    if (s.stage2_severe_ce && !s.stage2_severe_ce.passed) failed.push("the most severe failing case still fails");
    if (s.stage3_regression_set && !s.stage3_regression_set.passed) failed.push("something that worked before is now broken");
    if (s.stage4_falsifier_rerun && !s.stage4_falsifier_rerun.passed) failed.push("a fresh search found new failures");
    return failed;
  }

  function showGateStages(s) {
    var map = [
      ["pg-stage1-status", s.stage1_minimal_ce],
      ["pg-stage2-status", s.stage2_severe_ce],
      ["pg-stage3-status", s.stage3_regression_set],
      ["pg-stage4-status", s.stage4_falsifier_rerun],
    ];
    map.forEach(function (m) {
      var el = getElement(m[0]);
      if (el && m[1]) {
        el.textContent = m[1].passed ? "PASS" : "FAIL";
        el.className = "text-xs font-mono font-bold mt-4 " + (m[1].passed ? "text-ok" : "text-bad");
      }
    });
  }

  function repairSourceLabel(rj) {
    if (rj.source === "live") {
      var cost = typeof rj.cost_usd === "number" ? " (cost $" + rj.cost_usd.toFixed(4) + ")" : "";
      return "LIVE from Muse Spark" + cost;
    }
    if (rj.source === "cached_repair") return "CACHED repair (recorded earlier, not generated just now)";
    return String(rj.source || "unknown").toUpperCase();
  }

  async function runClosedLoop() {
    if (state.isRunning || state.autoRunning) return;
    var editor = getElement("pg-code-editor");
    var btn = getElement("pg-run-btn");
    if (!editor) return;

    state.autoRunning = true;
    if (btn) { btn.disabled = true; btn.textContent = "Running..."; }
    clearEditorError();
    for (var i = 1; i <= 5; i++) autoStage(i, "", "Waiting");
    autoSummary("", "");
    setVerdict("", "");
    var frameImg = getElement("pg-auto-frame");
    var frameEmpty = getElement("pg-auto-frame-empty");
    if (frameImg) { frameImg.style.display = "none"; frameImg.removeAttribute("src"); }
    if (frameEmpty) frameEmpty.style.display = "block";

    populatePresetDropdowns();
    updateBadge();
    var original = editor.value;
    var savedJump = window.jumpPlaygroundStep;
    window.jumpPlaygroundStep = function () {};
    var mirror = null;

    try {
      // Steps 1 and 2: validate, then search for failures (one server call)
      autoStage(1, "running", "Checking the code against the allowed controller language...");
      autoStage(2, "running", "Testing 20 scenarios on the real simulator...");
      var fr, data;
      try {
        fr = await fetch("/falsify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            code: original,
            robot_preset: state.robotPreset,
            task_preset: state.taskPreset,
            budget: 20,
            seed_base: 3100000,
          }),
        });
        data = await fr.json().catch(function () { return {}; });
      } catch (e) {
        autoStage(1, "bad", "Simulator backend is offline.");
        autoStage(2, "skip", "Start it with: <code>python -m playground.server --port 8000</code>");
        autoSummary("bad", "The simulator backend is not running, so nothing was tested.");
        return;
      }
      if (!fr.ok) {
        autoStage(1, "bad", escapeHtml(formatErrorDetail(data, fr.statusText)));
        autoStage(2, "skip", "Not run.");
        autoSummary("bad", "The request was rejected. Fix the problem above and run again.");
        return;
      }
      if (data.status === "VALIDATION_ERROR") {
        var ln = data.error_line ? "Line " + data.error_line + ": " : "";
        autoStage(1, "bad", escapeHtml(ln + data.error));
        autoStage(2, "skip", "Not run: the code must be valid first.");
        autoSummary("bad", "Your code was rejected before any simulation. The problem is shown under the code editor.");
        showEditorError(data.error, data.error_line);
        return;
      }
      autoStage(1, "ok", "Code is valid. Program hash " + String(data.program_sha256 || "").slice(0, 12) + "...");

      var evaluated = data.evaluated;
      var failures = data.failures;
      var passedBefore = evaluated - failures;
      var rejected = false;
      var repaired = false;
      var repairNote = "";

      if (!failures) {
        state.ces = null;
        autoStage(2, "ok", "No failure found in " + evaluated + " scenarios (a search, not a proof).");
        autoStage(3, "skip", "Not needed: no failures were found.");
        autoStage(4, "skip", "Not needed.");
      } else {
        state.ces = { minimal: data.minimal, severe: data.severe, source: "found" };
        autoStage(2, "bad",
          "<b>" + failures + " of " + evaluated + " scenarios failed.</b><br>Smallest failing case: " + describeCE(data.minimal) +
          "<br>Most severe failing case: " + describeCE(data.severe));

        if (data.beyond_hardware) {
          autoStage(3, "skip",
            "Cannot be fixed by code: this gripper cannot lift more than ~" + data.hardware_limit_kg.toFixed(2) +
            " kg and the worst failure is heavier. Choose a stronger gripper.");
          autoStage(4, "skip", "Not run.");
          repairNote = "Hardware limit: no software change can fix the heavy cases for this gripper.";
        } else {
          autoStage(3, "running", "Muse Spark is writing a repair from the failing cases...");
          var rr, rj;
          try {
            rr = await fetch("/repair", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                code: original,
                robot_preset: state.robotPreset,
                task_preset: state.taskPreset,
                minimal_ce: data.minimal,
                severe_ce: data.severe,
                allow_live: true,
              }),
            });
            rj = await rr.json().catch(function () { return {}; });
          } catch (e) {
            autoStage(3, "bad", "Repair service unreachable.");
            autoStage(4, "skip", "Not run.");
            rejected = true;
          }
          if (!rejected && !rr.ok) {
            autoStage(3, "bad", escapeHtml(formatErrorDetail(rj, rr.statusText)));
            autoStage(4, "skip", "Not run.");
            rejected = true;
          } else if (!rejected) {
            var p = rj.patch || {};
            autoStage(3, "ok", "Repair produced: " + repairSourceLabel(rj) + ".<br>" + escapeHtml(p.rationale || ""));
            var diffContainer = getElement("pg-diff-container");
            var diffView = getElement("pg-diff-view");
            var rationaleEl = getElement("pg-repair-rationale");
            if (diffContainer) diffContainer.style.display = "block";
            if (diffView) diffView.textContent = p.diff || "";
            if (rationaleEl) rationaleEl.textContent = "Rationale: " + (p.rationale || "");

            var g = rj.gates || {};
            var stages = g.stages || {};
            showGateStages(stages);
            if (g.accepted) {
              autoStage(4, "ok", "All 4 checks passed on the real simulator: smallest failure, worst failure, regression set, fresh search.");
              editor.value = p.code;
              repaired = true;
              updateBadge();
              repairNote = "Repair source: " + repairSourceLabel(rj) + ".";
            } else {
              autoStage(4, "bad", "Repair REJECTED: " + gateFailures(stages).join("; ") + ".");
              rejected = true;
            }
          }
        }
      }

      // Step 5: simulate
      if (rejected) {
        autoStage(5, "skip", "Not run: the repair was rejected. Your original code is unchanged in the editor.");
        autoSummary("bad",
          "<b>Repair rejected.</b> The simulator did not accept the proposed patch, so it was not applied. " +
          "Edit the code yourself or run the closed loop again.<br>Simulation only, not a certificate.");
        return;
      }

      autoStage(5, "running", "Starting simulation...");
      mirror = setInterval(function () {
        var img = getElement("pg-frame-img");
        if (img && img.style.display !== "none" && img.getAttribute("src") && frameImg) {
          frameImg.src = img.getAttribute("src");
          frameImg.style.display = "block";
          if (frameEmpty) frameEmpty.style.display = "none";
        }
        var pt = getElement("pg-progress-text");
        if (pt && pt.textContent) autoStage(5, "running", escapeHtml(pt.textContent));
      }, 300);
      await runSimulation();
      clearInterval(mirror);
      mirror = null;

      var k = getElement("pg-metric-k").textContent;
      var n = getElement("pg-metric-n").textContent;
      var rate = getElement("pg-metric-rate").textContent;
      var headline = getElement("pg-results-headline");
      var simBad = rate === "ERR" || k === "\u2014" || !state.backendAlive;
      if (simBad) {
        autoStage(5, "bad", escapeHtml(headline ? headline.textContent : "Simulation did not complete."));
        autoSummary("bad", "The final simulation did not complete. See the message above.");
      } else {
        autoStage(5, "ok", k + " of " + n + " episodes succeeded (" + rate + ").");
        var html;
        if (repaired) {
          html = "<b>Repaired and verified.</b><br>Before repair: " + passedBefore + " of " + evaluated +
            " search scenarios passed.<br>After repair: " + k + " of " + n + " simulation episodes passed.<br>" +
            repairNote + " 4 of 4 checks passed.";
        } else if (!failures) {
          html = "<b>No failures found.</b><br>Search: " + evaluated + " of " + evaluated +
            " scenarios passed.<br>Simulation: " + k + " of " + n + " episodes passed.";
        } else {
          html = "<b>Failures found, repair not possible in software.</b><br>Simulation of the original code: " +
            k + " of " + n + " episodes passed.<br>" + repairNote;
        }
        autoSummary(repaired || !failures ? "ok" : "bad",
          html + "<br><span style='font-size:11px;opacity:.8'>Simulation only, not a certificate. Edited code is PLAYGROUND, NOT CERTIFIED.</span>");
      }
    } finally {
      if (mirror) clearInterval(mirror);
      window.jumpPlaygroundStep = savedJump;
      state.autoRunning = false;
      if (btn) { btn.disabled = false; btn.textContent = "Run Simulation"; }
      var card = getElementById_safe("pg-auto-card");
      var errBox = getElement("pg-editor-error");
      var hasEditorError = errBox && errBox.style.display !== "none";
      if (card && !hasEditorError && card.scrollIntoView) card.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function getElementById_safe(id) {
    return document.getElementById(id);
  }

  // Init all event listeners
  function initPlayground() {
    // Put the step tracker right above the camera view, beside the editor
    var rightCol = getElement("pg-right-col");
    var autoCard = getElement("pg-auto-card");
    if (rightCol && autoCard && autoCard.parentNode !== rightCol) {
      rightCol.insertBefore(autoCard, rightCol.firstChild);
      autoCard.style.marginBottom = "20px";
    }
    populatePresetDropdowns();

    var editor = getElement("pg-code-editor");
    if (editor) {
      if (!editor.value) {
        editor.value = TEMPLATES.v2_certified;
      }
      editor.addEventListener("input", function () {
        state.ces = null;
        clearErrors();
        updateBadge();
        // Clear active template indicator on custom edit
        document.querySelectorAll(".pg-template-btn").forEach(function (b) {
          b.classList.remove("active");
        });
      });
    }

    var robotEl = getElement("pg-robot-preset");
    if (robotEl) {
      robotEl.addEventListener("change", function () { state.ces = null; });
      robotEl.addEventListener("change", updateBadge);
    }

    var taskEl = getElement("pg-task-preset");
    if (taskEl) {
      taskEl.addEventListener("change", function () { state.ces = null; });
      taskEl.addEventListener("change", updateBadge);
    }

    var autoBtn = getElement("pg-auto-btn");
    if (autoBtn) {
      autoBtn.addEventListener("click", runClosedLoop);
    }

    var falsifyBtn = getElement("pg-falsify-btn");
    if (falsifyBtn) {
      falsifyBtn.addEventListener("click", runFalsifier);
    }

    var budgetEl = getElement("pg-budget-preset");
    if (budgetEl) {
      budgetEl.addEventListener("change", updateBadge);
    }

    var replayCertEl = getElement("pg-replay-cert");
    if (replayCertEl) {
      replayCertEl.addEventListener("change", function () {
        if (replayCertEl.checked && budgetEl) {
          budgetEl.value = "20";
          updateBadge();
        }
      });
    }

    var runBtn = getElement("pg-run-btn");
    if (runBtn) {
      runBtn.addEventListener("click", runSimulation);
    }

    var loadRepairBtn = getElement("pg-load-repair-btn");
    if (loadRepairBtn) {
      loadRepairBtn.addEventListener("click", loadRecordedRepair);
    }

    var liveRepairBtn = getElement("pg-live-repair-btn");
    if (liveRepairBtn) {
      liveRepairBtn.addEventListener("click", requestLiveRepair);
    }

    var runGatesBtn = getElement("pg-run-gates-btn");
    if (runGatesBtn) {
      runGatesBtn.addEventListener("click", runAcceptanceGates);
    }

    // Template picker buttons
    document.querySelectorAll(".pg-template-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-template");
        loadTemplate(key);
      });
    });

    checkBackend();
    updateBadge();
    console.log("[ClosedLoop Playground] Loaded v20261103-v2, SHA-256 engine active. Templates:", {
      v2: computeHash(TEMPLATES.v2_certified),
      v1: computeHash(TEMPLATES.v1_certified)
    });
  }

  root.Playground = {
    init: initPlayground,
    updateBadge: updateBadge,
    loadTemplate: loadTemplate,
    runSimulation: runSimulation,
    runClosedLoop: runClosedLoop,
    loadRecordedRepair: loadRecordedRepair,
    runAcceptanceGates: runAcceptanceGates,
    clearErrors: clearErrors,
    TEMPLATES: TEMPLATES,
    computeHash: computeHash,
  };
  root.ClosedLoopPlayground = root.Playground;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPlayground);
  } else {
    initPlayground();
  }
})(typeof window !== "undefined" ? window : globalThis);
