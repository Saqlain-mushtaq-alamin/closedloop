/**
 * ClosedLoop Certificate Badge Evaluation (Plan §6.3, §13 PA1).
 *
 * Evaluates certificate binding to (program_sha256, robot_preset, task_preset, sim_code_sha256).
 */
(function (root) {
  function evaluateBadge(codeSha256, robotPreset, taskPreset, simCodeSha256, certificates) {
    var certs = certificates || (root.DATA && root.DATA.certificates) || [];

    // 1. Exact match on hash, robot, task, and simulator code hash
    for (var i = 0; i < certs.length; i++) {
      var cert = certs[i];
      if (
        cert.program_sha256 === codeSha256 &&
        cert.robot_preset === robotPreset &&
        cert.task_preset === taskPreset &&
        cert.sim_code_sha256 === simCodeSha256
      ) {
        return {
          status: "CERTIFIED",
          badge: "CERTIFIED",
          badgeClass: "badge-pill-pass",
          message:
            "Certified in simulation under distribution D (Run ID: " +
            cert.cert_id +
            ", evidence platform: " +
            (cert.evidence_platform || "win_amd64") +
            ").",
          cert_id: cert.cert_id,
          evidence_platform: cert.evidence_platform || "win_amd64",
        };
      }
    }

    // 2. Program hash matches a certificate, but robot, task, or environment differs
    for (var j = 0; j < certs.length; j++) {
      var c = certs[j];
      if (c.program_sha256 === codeSha256) {
        var reasons = [];
        if (c.robot_preset !== robotPreset) {
          reasons.push("robot '" + robotPreset + "' != certified '" + c.robot_preset + "'");
        }
        if (c.task_preset !== taskPreset) {
          reasons.push("task '" + taskPreset + "' != certified '" + c.task_preset + "'");
        }
        if (c.sim_code_sha256 !== simCodeSha256) {
          reasons.push("simulator code hash differs from evidence run");
        }

        return {
          status: "VOID_SETUP",
          badge: "VOID FOR THIS SETUP",
          badgeClass: "badge-pill-warn",
          message:
            "This program has a certificate (" +
            c.cert_id +
            "), but not for this setup: " +
            reasons.join(", ") +
            ".",
          cert_id: c.cert_id,
          evidence_platform: c.evidence_platform || "win_amd64",
        };
      }
    }

    // 3. No certificate found for this program hash
    return {
      status: "VOID",
      badge: "VOID",
      badgeClass: "badge-pill-fail",
      message: "This code has no certificate. Re-certify.",
      cert_id: null,
      evidence_platform: null,
    };
  }

  root.evaluateBadge = evaluateBadge;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { evaluateBadge: evaluateBadge };
  }
})(typeof window !== "undefined" ? window : globalThis);
