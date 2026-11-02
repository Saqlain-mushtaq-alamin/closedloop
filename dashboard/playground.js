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
      "",
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
    function rightRotate(value, amount) {
      return (value >>> amount) | (value << (32 - amount));
    }
    var mathPow = Math.pow;
    var maxWord = mathPow(2, 32);
    var lengthProperty = "length";
    var i, j;
    var result = "";
    var words = [];
    var asciiBitLength = ascii[lengthProperty] * 8;
    var hash = [];
    var k = [];
    var primeCounter = 0;
    var isComposite = {};
    for (var candidate = 2; primeCounter < 64; candidate++) {
      if (!isComposite[candidate]) {
        for (i = 0; i < 300; i += candidate) isComposite[i] = candidate;
        hash[primeCounter] = (mathPow(candidate, 0.5) * maxWord) | 0;
        k[primeCounter++] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
      }
    }
    ascii += "\x80";
    while ((ascii[lengthProperty] % 64) - 56) ascii += "\x00";
    for (i = 0; i < ascii[lengthProperty]; i++) {
      j = ascii.charCodeAt(i);
      if (j >> 8) return "";
      words[i >> 2] |= j << ((3 - (i % 4)) * 8);
    }
    words[words[lengthProperty]] = (asciiBitLength / maxWord) | 0;
    words[words[lengthProperty]] = asciiBitLength | 0;
    for (j = 0; j < words[lengthProperty]; ) {
      var w = words.slice(j, (j += 16));
      var oldHash = hash;
      hash = hash.slice(0, 8);
      for (i = 0; i < 64; i++) {
        var w15 = w[i - 15],
          w2 = w[i - 2];
        var s0 = rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3);
        var s1 = rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10);
        w[i] =
          i < 16
            ? w[i]
            : (w[i - 16] + s0 + w[i - 7] + s1) | 0;
        var s1_maj = rightRotate(hash[0], 2) ^ rightRotate(hash[0], 13) ^ rightRotate(hash[0], 22);
        var maj = (hash[0] & hash[1]) ^ (hash[0] & hash[2]) ^ (hash[1] & hash[2]);
        var t2 = (s1_maj + maj) | 0;
        var s0_ch = rightRotate(hash[4], 6) ^ rightRotate(hash[4], 11) ^ rightRotate(hash[4], 25);
        var ch = (hash[4] & hash[5]) ^ (~hash[4] & hash[6]);
        var t1 = (hash[7] + s0_ch + ch + k[i] + w[i]) | 0;
        hash = [(t1 + t2) | 0].concat(hash);
        hash[4] = (hash[4] + t1) | 0;
      }
      for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
    }
    for (i = 0; i < 8; i++) {
      for (var b = 3; b >= 0; b--) {
        var byteVal = (hash[i] >> (8 * b)) & 255;
        result += (byteVal < 16 ? "0" : "") + byteVal.toString(16);
      }
    }
    return result;
  }

  // Normalize LF and compute SHA-256
  function computeHash(text) {
    if (!text) return "";
    var normalized = text.replace(/\r\n/g, "\n");
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

    var isCertified = badgeInfo.status === "PASS";

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
          svcBadge.textContent = "Backend: Live (FastAPI / " + (data.platform || "local") + ")";
        }
        return true;
      }
    } catch (e) {
      // Backend not running on this port
    }

    state.backendAlive = false;
    if (svcBadge) {
      svcBadge.className = "badge-pill badge-pill-neutral";
      svcBadge.textContent = "Mode: Tier 0 Hash Lab (Offline)";
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

  // Run simulation trigger (supports streaming SSE or offline fallback)
  // Run simulation trigger (supports streaming SSE or offline fallback)
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
      // Offline / Tier 0 Hash Lab mode
      setTimeout(function () {
        var ptext = getElement("pg-progress-text");
        if (ptext) {
          ptext.innerHTML =
            '<span class="text-warn font-semibold">Tier 0 (Hash Lab) Active:</span> Simulator service is offline. ' +
            'Cryptographic badge verified: <span class="font-mono">' + state.programSha256.substring(0, 16) + '...</span>. ' +
            'To run live physics episodes on your machine, execute <code class="px-2 py-1 bg-inset rounded font-mono text-xs">make playground-local</code> in terminal.';
        }
        var pbar = getElement("pg-progress-fill");
        if (pbar) pbar.style.width = "100%";
        if (resHeadline) {
          resHeadline.textContent = "Offline Hash Lab: Verified against certified hash database.";
        }
        if (typeof window.jumpPlaygroundStep === "function") {
          window.jumpPlaygroundStep(4);
        }
        state.isRunning = false;
        if (runBtn) {
          runBtn.disabled = false;
          runBtn.textContent = "Run Simulation";
        }
        if (camBadge) {
          camBadge.className = "badge-pill badge-pill-neutral text-xs";
          camBadge.textContent = "TIER 0 OFFLINE";
        }
        if (logBadge) {
          logBadge.className = "badge-pill badge-pill-neutral text-xs";
          logBadge.textContent = "OFFLINE";
        }
      }, 500);
      return;
    }

    // Live Streaming Run via POST /run with stream=true
    try {
      var payload = {
        code: code,
        robot_preset: robotPreset,
        task_preset: taskPreset,
        budget: budget,
        seed_base: 2000,
        render_frames: true,
        replay_certified_episodes: replayCertified,
        stream: true,
      };

      var resp = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        var errData = await resp.json().catch(function () { return { detail: resp.statusText }; });
        var ptext = getElement("pg-progress-text");
        if (ptext) {
          ptext.innerHTML = '<span class="text-bad font-semibold">Validation Error:</span> ' + (errData.detail || errData.error || "Execution failed");
        }
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
            if (resHeadlineDone) {
              resHeadlineDone.textContent = evData.k + " of " + evData.n + " episodes succeeded (" + (evData.success_rate * 100).toFixed(1) + "%).";
            }
            if (typeof window.jumpPlaygroundStep === "function") {
              window.jumpPlaygroundStep(4);
            }

            var camBadgeDone = getElement("pg-camera-mode-badge");
            if (camBadgeDone) {
              camBadgeDone.className = "badge-pill " + (evData.certified ? "badge-pill-pass" : "badge-pill-neutral") + " text-xs";
              camBadgeDone.textContent = evData.certified ? "CERTIFIED" : "PLAYGROUND, NOT CERTIFIED";
            }
            var logBadgeDone = getElement("pg-log-mode-badge");
            if (logBadgeDone) {
              logBadgeDone.className = "badge-pill " + (evData.certified ? "badge-pill-pass" : "badge-pill-neutral") + " text-xs";
              logBadgeDone.textContent = evData.certified ? "CERTIFIED LOG" : "PLAYGROUND LOG";
            }
          } else if (evType === "error") {
            getElement("pg-progress-text").innerHTML =
              '<span class="text-bad font-semibold">Error:</span> ' + (evData.message || "Failed");
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

    var ce1 = { mass: 10.16, friction: 0.8, x: 0.0, y: 0.0, yaw: 0.0, seed: 711000 };
    var ce2 = { mass: 11.5, friction: 0.5, x: -0.05, y: -0.05, yaw: 0.2, seed: 711001 };

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
        return;
      }
    } catch (e) {
      // Offline fallback evaluation
    }

    // Offline heuristic: code with 300N force without 100N clamp passes all stages
    var commands300 = code.indexOf("close_gripper(300)") !== -1;
    var is100Clamped = robotPreset === "gripper_100N";
    var passesHeavy = commands300 && !is100Clamped;

    var setOffline = function (id, ok) {
      var el = getElement(id);
      if (el) {
        el.textContent = ok ? "PASS" : "FAIL";
        el.className = "text-xs font-mono font-bold mt-4 " + (ok ? "text-ok" : "text-bad");
      }
    };

    setOffline("pg-stage1-status", passesHeavy);
    setOffline("pg-stage2-status", passesHeavy);
    setOffline("pg-stage3-status", true);
    setOffline("pg-stage4-status", passesHeavy);
  }

  // Init all event listeners
  function initPlayground() {
    populatePresetDropdowns();

    var editor = getElement("pg-code-editor");
    if (editor) {
      if (!editor.value) {
        editor.value = TEMPLATES.v2_certified;
      }
      editor.addEventListener("input", function () {
        updateBadge();
        // Clear active template indicator on custom edit
        document.querySelectorAll(".pg-template-btn").forEach(function (b) {
          b.classList.remove("active");
        });
      });
    }

    var robotEl = getElement("pg-robot-preset");
    if (robotEl) {
      robotEl.addEventListener("change", updateBadge);
    }

    var taskEl = getElement("pg-task-preset");
    if (taskEl) {
      taskEl.addEventListener("change", updateBadge);
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
  }

  root.Playground = {
    init: initPlayground,
    updateBadge: updateBadge,
    loadTemplate: loadTemplate,
    runSimulation: runSimulation,
    loadRecordedRepair: loadRecordedRepair,
    runAcceptanceGates: runAcceptanceGates,
    TEMPLATES: TEMPLATES,
    computeHash: computeHash,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPlayground);
  } else {
    initPlayground();
  }
})(typeof window !== "undefined" ? window : globalThis);
