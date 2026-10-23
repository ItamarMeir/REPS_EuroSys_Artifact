LB1 (healthy single flow, rho=1) = 16.861 us

| p (%) | REPS | AR (q=193) | JSQ | Ofan (plain) | Ofan weighted | ideal (rate loss only) |
|---|---|---|---|---|---|---|
| 0 | 15.4 +- 0.2 (n=10) | 14.0 +- 0.3 (n=10) | 17.4 +- 0.4 (n=10) | 2.9 +- 0.0 (n=10) | - | 0.0 +- 0.0 |
| 0.5 | 24.2 +- 0.6 (n=30) | 23.3 +- 0.7 (n=30) | 23.0 +- 0.7 (n=30) | 16.8 +- 0.9 (n=30) | 15.4 +- 0.7 (n=30) | 13.5 +- 0.8 |
| 1 | 28.1 +- 2.5 (n=10) | 28.6 +- 2.1 (n=10) | 29.5 +- 2.8 (n=10) | 21.5 +- 2.6 (n=10) | 19.2 +- 2.3 (n=10) | 17.3 +- 2.3 |
| 1.5 | 34.7 +- 2.3 (n=10) | 33.8 +- 2.2 (n=10) | 33.1 +- 2.5 (n=10) | 29.3 +- 2.7 (n=10) | 27.5 +- 2.9 (n=10) | 25.8 +- 2.9 |
| 2 | 35.9 +- 1.6 (n=30) | 36.5 +- 1.7 (n=30) | 35.0 +- 1.6 (n=30) | 31.5 +- 1.8 (n=30) | 29.4 +- 1.7 (n=30) | 27.7 +- 1.7 |

Excess over each instance's own ideal (CCT / ideal CCT - 1, %), mean +- SEM:

| p (%) | REPS | AR (q=193) | JSQ | Ofan (plain) | Ofan weighted |
|---|---|---|---|---|---|
| 0 | 15.4 +- 0.2 | 14.0 +- 0.3 | 17.4 +- 0.4 | 2.9 +- 0.0 | - |
| 0.5 | 9.5 +- 0.7 | 8.8 +- 0.7 | 8.5 +- 0.9 | 3.0 +- 0.8 | 1.7 +- 0.1 |
| 1 | 9.2 +- 0.8 | 9.7 +- 0.9 | 10.4 +- 1.2 | 3.6 +- 0.9 | 1.6 +- 0.1 |
| 1.5 | 7.2 +- 1.0 | 6.5 +- 1.2 | 5.9 +- 1.2 | 2.9 +- 1.0 | 1.4 +- 0.1 |
| 2 | 6.5 +- 0.4 | 7.0 +- 0.6 | 5.8 +- 0.5 | 3.0 +- 0.6 | 1.3 +- 0.0 |

Max queue (4160 B packets, max over fabric layers), mean over seeds; drops/trims summed:

| p (%) | REPS | AR (q=193) | JSQ | Ofan (plain) | Ofan weighted |
|---|---|---|---|---|---|
| 0 | 52 / drops 0 | 46 / drops 0 | 66 / drops 0 | 8 / drops 0 | - |
| 0.5 | 42 / drops 0 | 38 / drops 0 | 41 / drops 0 | 14 / drops 0 | 8 / drops 0 |
| 1 | 48 / drops 0 | 44 / drops 0 | 51 / drops 0 | 17 / drops 0 | 7 / drops 0 |
| 1.5 | 39 / drops 0 | 35 / drops 0 | 32 / drops 0 | 15 / drops 0 | 7 / drops 0 |
| 2 | 39 / drops 0 | 36 / drops 0 | 32 / drops 0 | 15 / drops 0 | 7 / drops 0 |

Runs where not all flows finished: 0 of 440
