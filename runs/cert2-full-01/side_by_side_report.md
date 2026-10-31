# Side-by-Side Certification Report: v1 vs v2

> **Methodological Note (Rule H14):** v2 was created after seeing v1's certificate; v2's certificate is valid because v2 was fixed before its own data was drawn. Both programs are reported side by side.

## Summary Metrics
- **v1 (`bec73dec45a88431`):** Certified Area Fraction = 0.5000 (8/16 cells), Headline = 35/59 (p_L=0.4778, uncertified)
- **v2 (`5f74f7762ee1f378`):** Certified Area Fraction = 1.0000 (16/16 cells), Headline = 59/59 (p_L=0.9505, certified)

## Per-Cell Comparison Table (State Lower Bound p_L at delta=0.003125)
| Cell ID | Mass Range (kg) | Friction Range | v1 Pass Rate | v1 p_L | v1 Cert | v2 Pass Rate | v2 p_L | v2 Cert |
|---|---|---|---|---|---|---|---|---|
| cell_00 | [1.00, 3.62] | [0.10, 0.33] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_01 | [1.00, 3.62] | [0.33, 0.55] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_02 | [1.00, 3.62] | [0.55, 0.78] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_03 | [1.00, 3.62] | [0.78, 1.00] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_04 | [3.62, 6.25] | [0.10, 0.33] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_05 | [3.62, 6.25] | [0.33, 0.55] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_06 | [3.62, 6.25] | [0.55, 0.78] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_07 | [3.62, 6.25] | [0.78, 1.00] | 150/150 | 0.9623 | PASS | 150/150 | 0.9623 | PASS |
| cell_08 | [6.25, 8.88] | [0.10, 0.33] | 134/150 | 0.8068 | FAIL | 150/150 | 0.9623 | PASS |
| cell_09 | [6.25, 8.88] | [0.33, 0.55] | 130/150 | 0.7745 | FAIL | 150/150 | 0.9623 | PASS |
| cell_10 | [6.25, 8.88] | [0.55, 0.78] | 127/150 | 0.7509 | FAIL | 150/150 | 0.9623 | PASS |
| cell_11 | [6.25, 8.88] | [0.78, 1.00] | 129/150 | 0.7666 | FAIL | 150/150 | 0.9623 | PASS |
| cell_12 | [8.88, 11.50] | [0.10, 0.33] | 0/150 | 0.0000 | FAIL | 150/150 | 0.9623 | PASS |
| cell_13 | [8.88, 11.50] | [0.33, 0.55] | 0/150 | 0.0000 | FAIL | 150/150 | 0.9623 | PASS |
| cell_14 | [8.88, 11.50] | [0.55, 0.78] | 0/150 | 0.0000 | FAIL | 150/150 | 0.9623 | PASS |
| cell_15 | [8.88, 11.50] | [0.78, 1.00] | 0/150 | 0.0000 | FAIL | 150/150 | 0.9623 | PASS |

All results certified in simulation under distribution D using rendered camera footage and state truth.