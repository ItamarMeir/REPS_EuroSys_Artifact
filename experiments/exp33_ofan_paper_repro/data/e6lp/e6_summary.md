LB1 (healthy single flow, rho=1) = 16.861 us

| p (%) | REPS | AR (q=193) | JSQ | Ofan (plain) | Ofan weighted | ideal (rate loss only) |
|---|---|---|---|---|---|---|
| 0.5 | 25.1 +- 2.0 (n=10) | 23.0 +- 0.9 (n=10) | 23.9 +- 1.7 (n=10) | 17.6 +- 2.0 (n=10) | 14.3 +- 0.9 (n=10) | 11.7 +- 0.9 |
| 2 | 35.3 +- 2.5 (n=10) | 37.5 +- 3.1 (n=10) | 34.7 +- 2.5 (n=10) | 31.9 +- 3.2 (n=10) | 29.3 +- 2.6 (n=10) | 22.0 +- 3.1 |

Excess over each instance's own ideal (CCT / ideal CCT - 1, %), mean +- SEM:

| p (%) | REPS | AR (q=193) | JSQ | Ofan (plain) | Ofan weighted |
|---|---|---|---|---|---|
| 0.5 | 12.1 +- 1.8 | 10.2 +- 1.4 | 11.0 +- 1.9 | 5.4 +- 2.0 | 2.4 +- 0.4 |
| 2 | 11.2 +- 1.6 | 13.0 +- 2.7 | 10.7 +- 1.9 | 8.3 +- 2.2 | 6.1 +- 0.9 |

Max queue (4160 B packets, max over fabric layers), mean over seeds; drops/trims summed:

| p (%) | REPS | AR (q=193) | JSQ | Ofan (plain) | Ofan weighted |
|---|---|---|---|---|---|
| 0.5 | 51 / drops 0 | 43 / drops 0 | 50 / drops 0 | 22 / drops 0 | 9 / drops 0 |
| 2 | 58 / drops 0 | 61 / drops 0 | 54 / drops 0 | 39 / drops 0 | 28 / drops 0 |

Runs where not all flows finished: 0 of 100
