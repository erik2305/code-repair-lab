# CodeRepair Lab experiment analysis

Task is the primary analysis unit. This is a synthetic mechanism-study pilot,
not evidence of universal strategy superiority. Five repetitions do not
support inferential claims. Solve rates are not pooled across versions.

Functional-test success is a secondary diagnostic and does not replace the
preregistered evaluator-success outcome. Reproduction and full-suite must
exit 0 without timeout; lint is excluded. Lint-only failures stay failures.

## DEV-V3

Validated attempts: 110; tasks: 6.

### Primary independent evaluator outcomes

| Task | S0 | S1 | S2 | Agent |
| --- | --- | --- | --- | --- |
| dev-011 | 0/5 (0.0%) | 5/5 (100.0%) | 5/5 (100.0%) | 5/5 (100.0%) |
| dev-012 | 5/5 (100.0%) | 5/5 (100.0%) | 5/5 (100.0%) | 5/5 (100.0%) |
| dev-013 | 0/5 (0.0%) | 5/5 (100.0%) | 1/5 (20.0%) | 5/5 (100.0%) |
| dev-014 | 5/5 (100.0%) | 5/5 (100.0%) | 5/5 (100.0%) | 5/5 (100.0%) |
| dev-015 | 0/5 (0.0%) | N/A | 5/5 (100.0%) | 5/5 (100.0%) |
| dev-016 | 0/5 (0.0%) | N/A | 5/5 (100.0%) | 5/5 (100.0%) |

### Functional-test and lint diagnostics

| Task | Arm | Functional pass | Evaluator failures | Lint-only failures |
| --- | --- | --- | --- | --- |
| dev-011 | S0 | 0 | 5 | 0 |
| dev-011 | S1 | 5 | 0 | 0 |
| dev-011 | S2 | 5 | 0 | 0 |
| dev-011 | Agent | 5 | 0 | 0 |
| dev-012 | S0 | 5 | 0 | 0 |
| dev-012 | S1 | 5 | 0 | 0 |
| dev-012 | S2 | 5 | 0 | 0 |
| dev-012 | Agent | 5 | 0 | 0 |
| dev-013 | S0 | 0 | 5 | 0 |
| dev-013 | S1 | 5 | 0 | 0 |
| dev-013 | S2 | 5 | 4 | 4 |
| dev-013 | Agent | 5 | 0 | 0 |
| dev-014 | S0 | 5 | 0 | 0 |
| dev-014 | S1 | 5 | 0 | 0 |
| dev-014 | S2 | 5 | 0 | 0 |
| dev-014 | Agent | 5 | 0 | 0 |
| dev-015 | S0 | 0 | 5 | 0 |
| dev-015 | S2 | 5 | 0 | 0 |
| dev-015 | Agent | 5 | 0 | 0 |
| dev-016 | S0 | 0 | 5 | 0 |
| dev-016 | S2 | 5 | 0 | 0 |
| dev-016 | Agent | 5 | 0 | 0 |

### Resource measurements

Arm aggregates are descriptive telemetry; applicability sets differ.
Each metric reports available/missing counts; missing is not zero.

| Domain | Arm | Metric | Available | Missing | Total | Mean | Median | Min | Max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all applicable tasks | S0 | model_calls | 30 | 0 | 30 | 1 | 1 | 1 | 1 |
| all applicable tasks | S0 | tool_calls_total | 30 | 0 | 0 | 0 | 0 | 0 | 0 |
| all applicable tasks | S0 | input_tokens | 30 | 0 | 19750 | 658.3333333333334 | 671 | 489 | 806 |
| all applicable tasks | S0 | output_tokens | 30 | 0 | 9921 | 330.7 | 244 | 138 | 946 |
| all applicable tasks | S0 | total_tokens | 30 | 0 | 29671 | 989.0333333333333 | 922.5 | 782 | 1435 |
| all applicable tasks | S0 | cached_input_tokens | 30 | 0 | 0 | 0 | 0 | 0 | 0 |
| all applicable tasks | S0 | reasoning_output_tokens | 30 | 0 | 6098 | 203.26666666666668 | 104.5 | 33 | 823 |
| all applicable tasks | S0 | reported_cost_usd | 30 | 0 | 0.0069355 | 0.00023118333333333333 | 0.0001824 | 0.0001459 | 0.0005219 |
| all applicable tasks | S0 | model_latency_seconds | 30 | 0 | 136.79415690000224 | 4.559805230000075 | 3.544151950000014 | 2.4618000999998912 | 9.415505099999791 |
| all applicable tasks | S0 | strategy_duration_seconds | 30 | 0 | 204.9616477999989 | 6.83205492666663 | 5.7910987499999464 | 4.514191399999618 | 12.156473999999434 |
| all applicable tasks | S0 | fixed_evidence_duration_seconds | 0 | 30 | null | null | null | null | null |
| all applicable tasks | S1 | model_calls | 20 | 0 | 20 | 1 | 1 | 1 | 1 |
| all applicable tasks | S1 | tool_calls_total | 20 | 0 | 20 | 1 | 1 | 1 | 1 |
| all applicable tasks | S1 | input_tokens | 20 | 0 | 23202 | 1160.1 | 1147.5 | 700 | 1646 |
| all applicable tasks | S1 | output_tokens | 20 | 0 | 6103 | 305.15 | 238 | 133 | 685 |
| all applicable tasks | S1 | total_tokens | 20 | 0 | 29305 | 1465.25 | 1375 | 917 | 2325 |
| all applicable tasks | S1 | cached_input_tokens | 20 | 0 | 0 | 0 | 0 | 0 | 0 |
| all applicable tasks | S1 | reasoning_output_tokens | 20 | 0 | 3089 | 154.45 | 93 | 28 | 479 |
| all applicable tasks | S1 | reported_cost_usd | 20 | 0 | 0.00577175 | 0.0002885875 | 0.000247225 | 0.0001785 | 0.000547425 |
| all applicable tasks | S1 | model_latency_seconds | 20 | 0 | 91.09719409999252 | 4.554859704999626 | 3.773008199999822 | 2.2188769999993383 | 11.237902099999701 |
| all applicable tasks | S1 | strategy_duration_seconds | 20 | 0 | 146.98841319999974 | 7.349420659999987 | 6.388653900000463 | 5.111727899999096 | 13.830449600000065 |
| all applicable tasks | S1 | fixed_evidence_duration_seconds | 20 | 0 | 9.575728500000878 | 0.47878642500004387 | 0.5581889000004594 | 0.015185800000836025 | 1.1041010999997525 |
| all applicable tasks | S2 | model_calls | 30 | 0 | 60 | 2 | 2 | 2 | 2 |
| all applicable tasks | S2 | tool_calls_total | 30 | 0 | 30 | 1 | 1 | 1 | 1 |
| all applicable tasks | S2 | input_tokens | 30 | 0 | 57976 | 1932.5333333333333 | 2007 | 1319 | 2612 |
| all applicable tasks | S2 | output_tokens | 30 | 0 | 18593 | 619.7666666666667 | 548.5 | 185 | 1429 |
| all applicable tasks | S2 | total_tokens | 30 | 0 | 76569 | 2552.3 | 2442 | 1786 | 3833 |
| all applicable tasks | S2 | cached_input_tokens | 30 | 0 | 0 | 0 | 0 | 0 | 0 |
| all applicable tasks | S2 | reasoning_output_tokens | 30 | 0 | 11385 | 379.5 | 287.5 | 65 | 1164 |
| all applicable tasks | S2 | reported_cost_usd | 30 | 0 | 0.01583035 | 0.0005276783333333333 | 0.000495475 | 0.0003094 | 0.000917525 |
| all applicable tasks | S2 | model_latency_seconds | 30 | 0 | 277.72667439999805 | 9.257555813333267 | 8.092966849999812 | 3.8900467999992543 | 26.2573242999988 |
| all applicable tasks | S2 | strategy_duration_seconds | 30 | 0 | 362.52713640000457 | 12.084237880000153 | 10.943233199999668 | 6.699528099999952 | 29.27256099999977 |
| all applicable tasks | S2 | fixed_evidence_duration_seconds | 30 | 0 | 18.008351999997103 | 0.6002783999999034 | 0.8620140500006528 | 0.01498150000043097 | 1.0970452999990812 |
| all applicable tasks | Agent | model_calls | 30 | 0 | 191 | 6.366666666666666 | 6 | 4 | 8 |
| all applicable tasks | Agent | tool_calls_total | 30 | 0 | 161 | 5.366666666666666 | 5 | 3 | 7 |
| all applicable tasks | Agent | input_tokens | 30 | 0 | 323521 | 10784.033333333333 | 9827 | 5217 | 18851 |
| all applicable tasks | Agent | output_tokens | 30 | 0 | 21641 | 721.3666666666667 | 650 | 345 | 1362 |
| all applicable tasks | Agent | total_tokens | 30 | 0 | 345162 | 11505.4 | 10682.5 | 5665 | 20178 |
| all applicable tasks | Agent | cached_input_tokens | 30 | 0 | 86497 | 2883.233333333333 | 3525 | 0 | 6123 |
| all applicable tasks | Agent | reasoning_output_tokens | 30 | 0 | 12440 | 414.6666666666667 | 314 | 144 | 1054 |
| all applicable tasks | Agent | reported_cost_usd | 30 | 0 | 0.041244545 | 0.0013748181666666667 | 0.0012331325 | 0.00062179 | 0.002873225 |
| all applicable tasks | Agent | model_latency_seconds | 30 | 0 | 451.55579710000256 | 15.051859903333419 | 15.631317399999716 | 8.343017099999997 | 23.30487770000036 |
| all applicable tasks | Agent | strategy_duration_seconds | 30 | 0 | 581.5497559999967 | 19.384991866666557 | 20.367406749999645 | 11.898038999999699 | 28.645589200001268 |
| all applicable tasks | Agent | fixed_evidence_duration_seconds | 0 | 30 | null | null | null | null | null |
| dev-011 | S0 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-011 | S0 | tool_calls_total | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-011 | S0 | input_tokens | 5 | 0 | 2445 | 489 | 489 | 489 | 489 |
| dev-011 | S0 | output_tokens | 5 | 0 | 3910 | 782 | 882 | 579 | 946 |
| dev-011 | S0 | total_tokens | 5 | 0 | 6355 | 1271 | 1371 | 1068 | 1435 |
| dev-011 | S0 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-011 | S0 | reasoning_output_tokens | 5 | 0 | 3295 | 659 | 759 | 456 | 823 |
| dev-011 | S0 | reported_cost_usd | 5 | 0 | 0.0021995 | 0.0004399 | 0.0004899 | 0.0003384 | 0.0005219 |
| dev-011 | S0 | model_latency_seconds | 5 | 0 | 41.14896739999949 | 8.229793479999898 | 9.268260899999405 | 6.155209900000045 | 9.415505099999791 |
| dev-011 | S0 | strategy_duration_seconds | 5 | 0 | 53.661752400001205 | 10.73235048000024 | 11.33350960000007 | 8.887086300001101 | 12.146531599999435 |
| dev-011 | S0 | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-011 | S1 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-011 | S1 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-011 | S1 | input_tokens | 5 | 0 | 3500 | 700 | 700 | 700 | 700 |
| dev-011 | S1 | output_tokens | 5 | 0 | 1169 | 233.8 | 236 | 217 | 246 |
| dev-011 | S1 | total_tokens | 5 | 0 | 4669 | 933.8 | 936 | 917 | 946 |
| dev-011 | S1 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-011 | S1 | reasoning_output_tokens | 5 | 0 | 463 | 92.6 | 94 | 75 | 104 |
| dev-011 | S1 | reported_cost_usd | 5 | 0 | 0.0009345 | 0.0001869 | 0.000188 | 0.0001785 | 0.000193 |
| dev-011 | S1 | model_latency_seconds | 5 | 0 | 15.196470300000328 | 3.0392940600000657 | 3.0155782000001636 | 2.7105523999998695 | 3.2783927999998923 |
| dev-011 | S1 | strategy_duration_seconds | 5 | 0 | 27.74527809999836 | 5.549055619999672 | 5.423361600000135 | 5.324628799999118 | 5.931935099999464 |
| dev-011 | S1 | fixed_evidence_duration_seconds | 5 | 0 | 0.31179730000167183 | 0.06235946000033436 | 0.016188100000363193 | 0.015271400000528956 | 0.24754890000076557 |
| dev-011 | S2 | model_calls | 5 | 0 | 10 | 2 | 2 | 2 | 2 |
| dev-011 | S2 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-011 | S2 | input_tokens | 5 | 0 | 6595 | 1319 | 1319 | 1319 | 1319 |
| dev-011 | S2 | output_tokens | 5 | 0 | 5187 | 1037.4 | 1019 | 661 | 1429 |
| dev-011 | S2 | total_tokens | 5 | 0 | 11782 | 2356.4 | 2338 | 1980 | 2748 |
| dev-011 | S2 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-011 | S2 | reasoning_output_tokens | 5 | 0 | 3871 | 774.2 | 755 | 403 | 1164 |
| dev-011 | S2 | reported_cost_usd | 5 | 0 | 0.003253 | 0.0006506 | 0.0006414 | 0.0004624 | 0.0008464 |
| dev-011 | S2 | model_latency_seconds | 5 | 0 | 58.85790200000247 | 11.771580400000493 | 12.04024870000103 | 8.02655219999997 | 14.210885000000417 |
| dev-011 | S2 | strategy_duration_seconds | 5 | 0 | 70.54755090000162 | 14.109510180000324 | 14.782527200000914 | 10.228733099999772 | 16.85160689999975 |
| dev-011 | S2 | fixed_evidence_duration_seconds | 5 | 0 | 0.0769717999992281 | 0.01539435999984562 | 0.015112700000827317 | 0.01498150000043097 | 0.016382599999815284 |
| dev-011 | Agent | model_calls | 5 | 0 | 35 | 7 | 7 | 6 | 8 |
| dev-011 | Agent | tool_calls_total | 5 | 0 | 30 | 6 | 6 | 5 | 7 |
| dev-011 | Agent | input_tokens | 5 | 0 | 51258 | 10251.6 | 9835 | 7848 | 12219 |
| dev-011 | Agent | output_tokens | 5 | 0 | 2891 | 578.2 | 579 | 532 | 645 |
| dev-011 | Agent | total_tokens | 5 | 0 | 54149 | 10829.8 | 10414 | 8380 | 12801 |
| dev-011 | Agent | cached_input_tokens | 5 | 0 | 16447 | 3289.4 | 3430 | 0 | 6123 |
| dev-011 | Agent | reasoning_output_tokens | 5 | 0 | 1470 | 294 | 294 | 267 | 335 |
| dev-011 | Agent | reported_cost_usd | 5 | 0 | 0.00590412 | 0.001180824 | 0.00111065 | 0.000706625 | 0.001762275 |
| dev-011 | Agent | model_latency_seconds | 5 | 0 | 75.15992979999919 | 15.031985959999838 | 14.827304699998422 | 13.865677800001322 | 16.860037899999952 |
| dev-011 | Agent | strategy_duration_seconds | 5 | 0 | 96.55238939999981 | 19.31047787999996 | 18.95562599999903 | 17.79848679999941 | 20.609623700000157 |
| dev-011 | Agent | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-012 | S0 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-012 | S0 | tool_calls_total | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-012 | S0 | input_tokens | 5 | 0 | 2720 | 544 | 544 | 544 | 544 |
| dev-012 | S0 | output_tokens | 5 | 0 | 1267 | 253.4 | 247 | 238 | 279 |
| dev-012 | S0 | total_tokens | 5 | 0 | 3987 | 797.4 | 791 | 782 | 823 |
| dev-012 | S0 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-012 | S0 | reasoning_output_tokens | 5 | 0 | 415 | 83 | 82 | 67 | 105 |
| dev-012 | S0 | reported_cost_usd | 5 | 0 | 0.0009055 | 0.0001811 | 0.0001779 | 0.0001734 | 0.0001939 |
| dev-012 | S0 | model_latency_seconds | 5 | 0 | 16.609195300001375 | 3.321839060000275 | 3.304055000000517 | 2.74923950000084 | 4.131703499999276 |
| dev-012 | S0 | strategy_duration_seconds | 5 | 0 | 29.63597739999932 | 5.927195479999864 | 5.888478099999702 | 5.42417370000112 | 6.77493449999929 |
| dev-012 | S0 | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-012 | S1 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-012 | S1 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-012 | S1 | input_tokens | 5 | 0 | 3670 | 734 | 734 | 734 | 734 |
| dev-012 | S1 | output_tokens | 5 | 0 | 1310 | 262 | 241 | 232 | 318 |
| dev-012 | S1 | total_tokens | 5 | 0 | 4980 | 996 | 975 | 966 | 1052 |
| dev-012 | S1 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-012 | S1 | reasoning_output_tokens | 5 | 0 | 440 | 88 | 67 | 58 | 144 |
| dev-012 | S1 | reported_cost_usd | 5 | 0 | 0.001022 | 0.0002044 | 0.0001939 | 0.0001894 | 0.0002324 |
| dev-012 | S1 | model_latency_seconds | 5 | 0 | 26.94717319999836 | 5.389434639999672 | 3.9264750000002095 | 3.637251299998752 | 11.237902099999701 |
| dev-012 | S1 | strategy_duration_seconds | 5 | 0 | 40.07786049999959 | 8.015572099999918 | 6.623635799998738 | 6.2179744000004575 | 13.830449600000065 |
| dev-012 | S1 | fixed_evidence_duration_seconds | 5 | 0 | 0.0846296000017901 | 0.01692592000035802 | 0.015409199999339762 | 0.015185800000836025 | 0.023291800000151852 |
| dev-012 | S2 | model_calls | 5 | 0 | 10 | 2 | 2 | 2 | 2 |
| dev-012 | S2 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-012 | S2 | input_tokens | 5 | 0 | 7286 | 1457.2 | 1459 | 1450 | 1459 |
| dev-012 | S2 | output_tokens | 5 | 0 | 1738 | 347.6 | 345 | 327 | 368 |
| dev-012 | S2 | total_tokens | 5 | 0 | 9024 | 1804.8 | 1804 | 1786 | 1827 |
| dev-012 | S2 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-012 | S2 | reasoning_output_tokens | 5 | 0 | 802 | 160.4 | 156 | 138 | 179 |
| dev-012 | S2 | reported_cost_usd | 5 | 0 | 0.0015976 | 0.00031952 | 0.0003184 | 0.0003094 | 0.0003299 |
| dev-012 | S2 | model_latency_seconds | 5 | 0 | 34.35997529999986 | 6.871995059999972 | 6.966497399998843 | 4.836325400001442 | 9.33082960000138 |
| dev-012 | S2 | strategy_duration_seconds | 5 | 0 | 47.648384399999486 | 9.529676879999897 | 9.70259679999981 | 7.444814399999814 | 12.084065200000623 |
| dev-012 | S2 | fixed_evidence_duration_seconds | 5 | 0 | 0.08065219999843976 | 0.01613043999968795 | 0.015347900000051595 | 0.015055599998959224 | 0.019250800000008894 |
| dev-012 | Agent | model_calls | 5 | 0 | 24 | 4.8 | 5 | 4 | 5 |
| dev-012 | Agent | tool_calls_total | 5 | 0 | 19 | 3.8 | 4 | 3 | 4 |
| dev-012 | Agent | input_tokens | 5 | 0 | 33223 | 6644.6 | 7007 | 5217 | 7011 |
| dev-012 | Agent | output_tokens | 5 | 0 | 2295 | 459 | 448 | 409 | 513 |
| dev-012 | Agent | total_tokens | 5 | 0 | 35518 | 7103.6 | 7442 | 5665 | 7499 |
| dev-012 | Agent | cached_input_tokens | 5 | 0 | 11468 | 2293.6 | 2209 | 0 | 3525 |
| dev-012 | Agent | reasoning_output_tokens | 5 | 0 | 999 | 199.8 | 203 | 144 | 257 |
| dev-012 | Agent | reported_cost_usd | 5 | 0 | 0.003979755 | 0.0007959509999999999 | 0.0007153750000000001 | 0.00062179 | 0.001093 |
| dev-012 | Agent | model_latency_seconds | 5 | 0 | 52.76963320000323 | 10.553926640000645 | 10.828394600001047 | 8.343017099999997 | 12.638207100000727 |
| dev-012 | Agent | strategy_duration_seconds | 5 | 0 | 75.33894419999888 | 15.067788839999775 | 15.429018700000597 | 11.898038999999699 | 17.70711619999929 |
| dev-012 | Agent | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-013 | S0 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-013 | S0 | tool_calls_total | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-013 | S0 | input_tokens | 5 | 0 | 4030 | 806 | 806 | 806 | 806 |
| dev-013 | S0 | output_tokens | 5 | 0 | 1784 | 356.8 | 322 | 315 | 454 |
| dev-013 | S0 | total_tokens | 5 | 0 | 5814 | 1162.8 | 1128 | 1121 | 1260 |
| dev-013 | S0 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-013 | S0 | reasoning_output_tokens | 5 | 0 | 1063 | 212.6 | 183 | 163 | 302 |
| dev-013 | S0 | reported_cost_usd | 5 | 0 | 0.001295 | 0.000259 | 0.0002416 | 0.0002381 | 0.0003076 |
| dev-013 | S0 | model_latency_seconds | 5 | 0 | 30.068086200000835 | 6.013617240000167 | 5.450910800000202 | 4.225924299998951 | 9.34082540000054 |
| dev-013 | S0 | strategy_duration_seconds | 5 | 0 | 41.46816529999887 | 8.293633059999774 | 7.590934699999707 | 6.3995255999998335 | 12.156473999999434 |
| dev-013 | S0 | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-013 | S1 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-013 | S1 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-013 | S1 | input_tokens | 5 | 0 | 8210 | 1642 | 1640 | 1639 | 1646 |
| dev-013 | S1 | output_tokens | 5 | 0 | 2904 | 580.8 | 566 | 512 | 685 |
| dev-013 | S1 | total_tokens | 5 | 0 | 11114 | 2222.8 | 2205 | 2152 | 2325 |
| dev-013 | S1 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-013 | S1 | reasoning_output_tokens | 5 | 0 | 1991 | 398.2 | 399 | 307 | 479 |
| dev-013 | S1 | reported_cost_usd | 5 | 0 | 0.002477875 | 0.000495575 | 0.0004878 | 0.000460925 | 0.000547425 |
| dev-013 | S1 | model_latency_seconds | 5 | 0 | 34.77388379999866 | 6.954776759999731 | 6.8273836999997 | 6.258345599999302 | 7.824088900000788 |
| dev-013 | S1 | strategy_duration_seconds | 5 | 0 | 50.352131100002225 | 10.070426220000446 | 9.746907900000224 | 9.206530600000406 | 11.165782300000501 |
| dev-013 | S1 | fixed_evidence_duration_seconds | 5 | 0 | 4.674072599998908 | 0.9348145199997816 | 0.8979438999995182 | 0.8750584999997955 | 1.1041010999997525 |
| dev-013 | S2 | model_calls | 5 | 0 | 10 | 2 | 2 | 2 | 2 |
| dev-013 | S2 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-013 | S2 | input_tokens | 5 | 0 | 13018 | 2603.6 | 2602 | 2597 | 2612 |
| dev-013 | S2 | output_tokens | 5 | 0 | 4856 | 971.2 | 924 | 769 | 1223 |
| dev-013 | S2 | total_tokens | 5 | 0 | 17874 | 3574.8 | 3526 | 3366 | 3833 |
| dev-013 | S2 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-013 | S2 | reasoning_output_tokens | 5 | 0 | 3157 | 631.4 | 547 | 466 | 894 |
| dev-013 | S2 | reported_cost_usd | 5 | 0 | 0.003954125 | 0.000790825 | 0.000767025 | 0.0006889 | 0.000917525 |
| dev-013 | S2 | model_latency_seconds | 5 | 0 | 81.36432340000101 | 16.272864680000204 | 12.126197000001412 | 11.432303199999296 | 26.2573242999988 |
| dev-013 | S2 | strategy_duration_seconds | 5 | 0 | 96.97470219999923 | 19.394940439999846 | 15.894955499999924 | 14.35525830000006 | 29.27256099999977 |
| dev-013 | S2 | fixed_evidence_duration_seconds | 5 | 0 | 4.712721699997928 | 0.9425443399995856 | 0.9142457999987528 | 0.8931895999994595 | 1.0970452999990812 |
| dev-013 | Agent | model_calls | 5 | 0 | 31 | 6.2 | 6 | 6 | 7 |
| dev-013 | Agent | tool_calls_total | 5 | 0 | 26 | 5.2 | 5 | 5 | 6 |
| dev-013 | Agent | input_tokens | 5 | 0 | 54082 | 10816.4 | 9816 | 9718 | 15006 |
| dev-013 | Agent | output_tokens | 5 | 0 | 5070 | 1014 | 920 | 870 | 1362 |
| dev-013 | Agent | total_tokens | 5 | 0 | 59152 | 11830.4 | 10741 | 10588 | 16368 |
| dev-013 | Agent | cached_input_tokens | 5 | 0 | 16763 | 3352.6 | 4152 | 0 | 5724 |
| dev-013 | Agent | reasoning_output_tokens | 5 | 0 | 3704 | 740.8 | 653 | 620 | 1054 |
| dev-013 | Agent | reported_cost_usd | 5 | 0 | 0.00736518 | 0.001473036 | 0.00125657 | 0.001007915 | 0.0022417 |
| dev-013 | Agent | model_latency_seconds | 5 | 0 | 92.57739079999737 | 18.515478159999475 | 17.336974300000293 | 16.646288399997502 | 21.394729800000277 |
| dev-013 | Agent | strategy_duration_seconds | 5 | 0 | 114.19578470000124 | 22.839156940000247 | 21.907888200001253 | 20.3848825999994 | 27.285403199999564 |
| dev-013 | Agent | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-014 | S0 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-014 | S0 | tool_calls_total | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-014 | S0 | input_tokens | 5 | 0 | 3845 | 769 | 769 | 769 | 769 |
| dev-014 | S0 | output_tokens | 5 | 0 | 810 | 162 | 156 | 138 | 203 |
| dev-014 | S0 | total_tokens | 5 | 0 | 4655 | 931 | 925 | 907 | 972 |
| dev-014 | S0 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-014 | S0 | reasoning_output_tokens | 5 | 0 | 285 | 57 | 51 | 33 | 98 |
| dev-014 | S0 | reported_cost_usd | 5 | 0 | 0.0007895 | 0.0001579 | 0.0001549 | 0.0001459 | 0.0001784 |
| dev-014 | S0 | model_latency_seconds | 5 | 0 | 15.392727299997205 | 3.078545459999441 | 2.8550063999991835 | 2.4618000999998912 | 4.105804499999067 |
| dev-014 | S0 | strategy_duration_seconds | 5 | 0 | 25.822741100000712 | 5.1645482200001425 | 5.091491099999985 | 4.514191399999618 | 6.159437500000422 |
| dev-014 | S0 | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-014 | S1 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-014 | S1 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-014 | S1 | input_tokens | 5 | 0 | 7822 | 1564.4 | 1564 | 1561 | 1570 |
| dev-014 | S1 | output_tokens | 5 | 0 | 720 | 144 | 147 | 133 | 149 |
| dev-014 | S1 | total_tokens | 5 | 0 | 8542 | 1708.4 | 1709 | 1698 | 1714 |
| dev-014 | S1 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-014 | S1 | reasoning_output_tokens | 5 | 0 | 195 | 39 | 42 | 28 | 44 |
| dev-014 | S1 | reported_cost_usd | 5 | 0 | 0.001337375 | 0.000267475 | 0.00026855 | 0.00026205 | 0.000269925 |
| dev-014 | S1 | model_latency_seconds | 5 | 0 | 14.179666799995175 | 2.8359333599990353 | 2.2633715999982087 | 2.2188769999993383 | 4.802813999998762 |
| dev-014 | S1 | strategy_duration_seconds | 5 | 0 | 28.81314349999957 | 5.762628699999914 | 5.188340700000481 | 5.111727899999096 | 7.7101803999994445 |
| dev-014 | S1 | fixed_evidence_duration_seconds | 5 | 0 | 4.505228999998508 | 0.9010457999997016 | 0.8983221999988018 | 0.8688289000001532 | 0.9448045000008278 |
| dev-014 | S2 | model_calls | 5 | 0 | 10 | 2 | 2 | 2 | 2 |
| dev-014 | S2 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-014 | S2 | input_tokens | 5 | 0 | 10039 | 2007.8 | 2008 | 2003 | 2013 |
| dev-014 | S2 | output_tokens | 5 | 0 | 1040 | 208 | 198 | 185 | 252 |
| dev-014 | S2 | total_tokens | 5 | 0 | 11079 | 2215.8 | 2208 | 2188 | 2260 |
| dev-014 | S2 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-014 | S2 | reasoning_output_tokens | 5 | 0 | 440 | 88 | 78 | 65 | 132 |
| dev-014 | S2 | reported_cost_usd | 5 | 0 | 0.001678375 | 0.000335675 | 0.00033045 | 0.000323575 | 0.00035769999999999997 |
| dev-014 | S2 | model_latency_seconds | 5 | 0 | 23.545514999996158 | 4.7091029999992315 | 4.764924200000678 | 3.8900467999992543 | 5.2597549999991315 |
| dev-014 | S2 | strategy_duration_seconds | 5 | 0 | 38.68685210000331 | 7.737370420000661 | 7.668946600000709 | 6.699528099999952 | 8.984826200001407 |
| dev-014 | S2 | fixed_evidence_duration_seconds | 5 | 0 | 4.350187399999413 | 0.8700374799998826 | 0.8279155000000173 | 0.7905498999989504 | 1.0774495999994542 |
| dev-014 | Agent | model_calls | 5 | 0 | 25 | 5 | 5 | 5 | 5 |
| dev-014 | Agent | tool_calls_total | 5 | 0 | 20 | 4 | 4 | 4 | 4 |
| dev-014 | Agent | input_tokens | 5 | 0 | 39489 | 7897.8 | 7898 | 7896 | 7899 |
| dev-014 | Agent | output_tokens | 5 | 0 | 1768 | 353.6 | 353 | 345 | 368 |
| dev-014 | Agent | total_tokens | 5 | 0 | 41257 | 8251.4 | 8249 | 8244 | 8266 |
| dev-014 | Agent | cached_input_tokens | 5 | 0 | 16488 | 3297.6 | 4122 | 0 | 4122 |
| dev-014 | Agent | reasoning_output_tokens | 5 | 0 | 788 | 157.6 | 157 | 149 | 172 |
| dev-014 | Agent | reported_cost_usd | 5 | 0 | 0.00392213 | 0.000784426 | 0.00068997 | 0.00068672 | 0.0011595 |
| dev-014 | Agent | model_latency_seconds | 5 | 0 | 47.34772869999688 | 9.469545739999376 | 9.392936899997949 | 8.932555899998988 | 10.16423130000112 |
| dev-014 | Agent | strategy_duration_seconds | 5 | 0 | 65.83393329999672 | 13.166786659999342 | 13.10151549999864 | 12.59798950000004 | 13.858732200000304 |
| dev-014 | Agent | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-015 | S0 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-015 | S0 | tool_calls_total | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-015 | S0 | input_tokens | 5 | 0 | 3620 | 724 | 724 | 724 | 724 |
| dev-015 | S0 | output_tokens | 5 | 0 | 998 | 199.6 | 192 | 176 | 233 |
| dev-015 | S0 | total_tokens | 5 | 0 | 4618 | 923.6 | 916 | 900 | 957 |
| dev-015 | S0 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-015 | S0 | reasoning_output_tokens | 5 | 0 | 448 | 89.6 | 82 | 66 | 123 |
| dev-015 | S0 | reported_cost_usd | 5 | 0 | 0.000861 | 0.0001722 | 0.0001684 | 0.0001604 | 0.0001889 |
| dev-015 | S0 | model_latency_seconds | 5 | 0 | 16.04966609999974 | 3.209933219999948 | 3.138122000000294 | 2.8607169999995676 | 3.5812095000001136 |
| dev-015 | S0 | strategy_duration_seconds | 5 | 0 | 26.407836399999724 | 5.281567279999945 | 5.2053508999997575 | 4.942215600000054 | 5.675348500000837 |
| dev-015 | S0 | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-015 | S2 | model_calls | 5 | 0 | 10 | 2 | 2 | 2 | 2 |
| dev-015 | S2 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-015 | S2 | input_tokens | 5 | 0 | 11008 | 2201.6 | 2202 | 2198 | 2205 |
| dev-015 | S2 | output_tokens | 5 | 0 | 3353 | 670.6 | 621 | 567 | 823 |
| dev-015 | S2 | total_tokens | 5 | 0 | 14361 | 2872.2 | 2821 | 2772 | 3021 |
| dev-015 | S2 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-015 | S2 | reasoning_output_tokens | 5 | 0 | 1911 | 382.2 | 331 | 288 | 518 |
| dev-015 | S2 | reported_cost_usd | 5 | 0 | 0.002961625 | 0.000592325 | 0.000567325 | 0.00054095 | 0.000668075 |
| dev-015 | S2 | model_latency_seconds | 5 | 0 | 44.71605390000332 | 8.943210780000664 | 9.176087499999994 | 7.878608099999838 | 9.706121600000188 |
| dev-015 | S2 | strategy_duration_seconds | 5 | 0 | 59.26347840000017 | 11.852695680000034 | 12.13887650000106 | 10.7927796999993 | 12.611205700000937 |
| dev-015 | S2 | fixed_evidence_duration_seconds | 5 | 0 | 4.403191200000947 | 0.8806382400001894 | 0.8685181999990164 | 0.8634565000011207 | 0.9191508000003523 |
| dev-015 | Agent | model_calls | 5 | 0 | 39 | 7.8 | 8 | 7 | 8 |
| dev-015 | Agent | tool_calls_total | 5 | 0 | 34 | 6.8 | 7 | 6 | 7 |
| dev-015 | Agent | input_tokens | 5 | 0 | 78553 | 15710.6 | 15619 | 12880 | 18851 |
| dev-015 | Agent | output_tokens | 5 | 0 | 5660 | 1132 | 1184 | 928 | 1327 |
| dev-015 | Agent | total_tokens | 5 | 0 | 84213 | 16842.6 | 16788 | 13808 | 20178 |
| dev-015 | Agent | cached_input_tokens | 5 | 0 | 13261 | 2652.2 | 3997 | 0 | 3997 |
| dev-015 | Agent | reasoning_output_tokens | 5 | 0 | 3501 | 700.2 | 739 | 525 | 893 |
| dev-015 | Agent | reported_cost_usd | 5 | 0 | 0.011121185 | 0.002224237 | 0.0020916199999999998 | 0.00161382 | 0.002873225 |
| dev-015 | Agent | model_latency_seconds | 5 | 0 | 101.01997549999578 | 20.203995099999155 | 20.738494999997783 | 17.61617529999603 | 23.30487770000036 |
| dev-015 | Agent | strategy_duration_seconds | 5 | 0 | 124.28362980000202 | 24.856725960000404 | 25.275862899999993 | 22.118880199999694 | 28.645589200001268 |
| dev-015 | Agent | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-016 | S0 | model_calls | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-016 | S0 | tool_calls_total | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-016 | S0 | input_tokens | 5 | 0 | 3090 | 618 | 618 | 618 | 618 |
| dev-016 | S0 | output_tokens | 5 | 0 | 1152 | 230.4 | 228 | 174 | 287 |
| dev-016 | S0 | total_tokens | 5 | 0 | 4242 | 848.4 | 846 | 792 | 905 |
| dev-016 | S0 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-016 | S0 | reasoning_output_tokens | 5 | 0 | 592 | 118.4 | 116 | 62 | 175 |
| dev-016 | S0 | reported_cost_usd | 5 | 0 | 0.000885 | 0.000177 | 0.0001758 | 0.0001488 | 0.0002053 |
| dev-016 | S0 | model_latency_seconds | 5 | 0 | 17.52551460000359 | 3.5051029200007178 | 3.3372035000011238 | 3.038245100000495 | 4.303462699999727 |
| dev-016 | S0 | strategy_duration_seconds | 5 | 0 | 27.965175199999067 | 5.593035039999813 | 5.453332900000532 | 5.096488600000157 | 6.43629829999918 |
| dev-016 | S0 | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |
| dev-016 | S2 | model_calls | 5 | 0 | 10 | 2 | 2 | 2 | 2 |
| dev-016 | S2 | tool_calls_total | 5 | 0 | 5 | 1 | 1 | 1 | 1 |
| dev-016 | S2 | input_tokens | 5 | 0 | 10030 | 2006 | 2006 | 1999 | 2011 |
| dev-016 | S2 | output_tokens | 5 | 0 | 2419 | 483.8 | 507 | 433 | 530 |
| dev-016 | S2 | total_tokens | 5 | 0 | 12449 | 2489.8 | 2506 | 2439 | 2539 |
| dev-016 | S2 | cached_input_tokens | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev-016 | S2 | reasoning_output_tokens | 5 | 0 | 1204 | 240.8 | 264 | 190 | 287 |
| dev-016 | S2 | reported_cost_usd | 5 | 0 | 0.0023856249999999997 | 0.00047712499999999996 | 0.00048784999999999996 | 0.000451725 | 0.0005005999999999999 |
| dev-016 | S2 | model_latency_seconds | 5 | 0 | 34.88290479999523 | 6.976580959999046 | 6.72620839999945 | 6.469504399998186 | 8.159381499999654 |
| dev-016 | S2 | strategy_duration_seconds | 5 | 0 | 49.40616840000075 | 9.88123368000015 | 9.62417330000062 | 9.345936300000176 | 11.093686700000035 |
| dev-016 | S2 | fixed_evidence_duration_seconds | 5 | 0 | 4.384627700001147 | 0.8769255400002294 | 0.8785766999990301 | 0.8605716000001848 | 0.8911936000004061 |
| dev-016 | Agent | model_calls | 5 | 0 | 37 | 7.4 | 8 | 6 | 8 |
| dev-016 | Agent | tool_calls_total | 5 | 0 | 32 | 6.4 | 7 | 5 | 7 |
| dev-016 | Agent | input_tokens | 5 | 0 | 66916 | 13383.2 | 14450 | 10350 | 14695 |
| dev-016 | Agent | output_tokens | 5 | 0 | 3957 | 791.4 | 778 | 655 | 966 |
| dev-016 | Agent | total_tokens | 5 | 0 | 70873 | 14174.6 | 15389 | 11005 | 15554 |
| dev-016 | Agent | cached_input_tokens | 5 | 0 | 12070 | 2414 | 2357 | 0 | 3678 |
| dev-016 | Agent | reasoning_output_tokens | 5 | 0 | 1978 | 395.6 | 415 | 312 | 472 |
| dev-016 | Agent | reported_cost_usd | 5 | 0 | 0.008952175 | 0.001790435 | 0.00176218 | 0.0016208 | 0.002017595 |
| dev-016 | Agent | model_latency_seconds | 5 | 0 | 82.68113910001011 | 16.536227820002022 | 16.494063000003734 | 14.2708823999983 | 18.623358000006192 |
| dev-016 | Agent | strategy_duration_seconds | 5 | 0 | 105.34507459999804 | 21.06901491999961 | 21.01699749999898 | 18.764508099999148 | 23.14564209999844 |
| dev-016 | Agent | fixed_evidence_duration_seconds | 0 | 5 | null | null | null | null | null |

### Run identity and environment

```json
{
  "configuration": {
    "docker_image_id": "sha256:4d8f71c8c6ab867e2abf876cf168bc9bc87076851140c46086e4d5655402fae0",
    "evaluator_timeout_seconds": 30,
    "experiment_id": "20261002T114122881026Z",
    "git_commit": "0c6841454e443ab21903c1bd8edd19e3fda3752c",
    "max_file_bytes": 100000,
    "max_output_tokens": 4096,
    "max_total_bytes": 200000,
    "model": "openai/gpt-6-luna",
    "reasoning_effort": "medium",
    "request_timeout_seconds": 60,
    "requested_model": "openai/gpt-6-luna",
    "routing_policy": {
      "cross_model_fallback": false,
      "require_parameters": true,
      "same_model_provider_fallback": true
    }
  },
  "configured_agent_limits": {
    "max_model_calls": 8,
    "max_tool_calls": 7,
    "max_transcript_bytes": 200000
  },
  "environment": {
    "configured_docker_image": [
      "coderepair-lab-sandbox:dev"
    ],
    "dependency_versions": [
      {
        "mcp": "2.2.0",
        "openai": "3.19.2",
        "pydantic": "2.13.5"
      }
    ],
    "docker_image_id": [
      "sha256:4d8f71c8c6ab867e2abf876cf168bc9bc87076851140c46086e4d5655402fae0"
    ],
    "inter_attempt_delay_seconds": [
      20
    ],
    "platform": [
      "Windows-11-10.0.26300-SP0"
    ],
    "python_version": [
      "3.13.15"
    ]
  },
  "returned_models": [
    "openai/gpt-6-luna"
  ],
  "routed_providers": [
    "OpenAI"
  ]
}
```

### S2 mechanism measurements

| Task | attempts | successes | functional_tests_passed | first_patch_shadow_success | first_patch_shadow_failure | first_patch_shadow_missing | fixed_probe_executed | second_generation | second_patch_nonempty | second_patch_empty | lint_only_failures | post_feedback_functional_recovery |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev-011 | 5 | 5 | 5 | 0 | 5 | 0 | 5 | 5 | 5 | 0 | 0 | 5 |
| dev-012 | 5 | 5 | 5 | 5 | 0 | 0 | 5 | 5 | 0 | 5 | 0 | 0 |
| dev-013 | 5 | 1 | 5 | 0 | 5 | 0 | 5 | 5 | 5 | 0 | 4 | 5 |
| dev-014 | 5 | 5 | 5 | 5 | 0 | 0 | 5 | 5 | 0 | 5 | 0 | 0 |
| dev-015 | 5 | 5 | 5 | 0 | 5 | 0 | 5 | 5 | 5 | 0 | 0 | 5 |
| dev-016 | 5 | 5 | 5 | 0 | 5 | 0 | 5 | 5 | 5 | 0 | 0 | 5 |

Recovery describes an observed transition, not causal necessity.

### Agent occurrence and mutation prefixes

| Task | none | tool_assisted_one_patch | context_refinement_iteration | feedback_responsive_iteration | Mutation prefixes | First prefix passed | Multiple mutations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev-011 | 0 | 5 | 0 | 0 | 5 | 5 | 0 |
| dev-012 | 0 | 5 | 0 | 0 | 5 | 5 | 0 |
| dev-013 | 0 | 5 | 0 | 0 | 5 | 5 | 0 |
| dev-014 | 0 | 5 | 0 | 0 | 5 | 5 | 0 |
| dev-015 | 0 | 0 | 0 | 5 | 10 | 0 | 5 |
| dev-016 | 0 | 0 | 0 | 5 | 11 | 0 | 5 |
| overall | 0 | 20 | 0 | 10 | 41 | 20 | 10 |

Tool use before one correct patch is not repair after a failed patch.

| Task | Exact action sequence | Count |
| --- | --- | --- |
| dev-011 | read_file → read_file → apply_file_changes → read_file → run_reproduction → finish | 1 |
| dev-011 | read_file → read_file → apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 2 |
| dev-011 | read_file → read_file → read_file → apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 1 |
| dev-011 | read_file → run_reproduction → apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 1 |
| dev-012 | apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 4 |
| dev-012 | apply_file_changes → run_reproduction → read_file → finish | 1 |
| dev-013 | read_file → apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 4 |
| dev-013 | read_file → run_reproduction → apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 1 |
| dev-014 | apply_file_changes → read_file → run_reproduction → run_full_tests → finish | 5 |
| dev-015 | apply_file_changes → read_file → run_reproduction → run_full_tests → apply_file_changes → read_file → run_full_tests → finish | 3 |
| dev-015 | apply_file_changes → read_file → run_reproduction → run_full_tests → apply_file_changes → run_full_tests → finish | 1 |
| dev-015 | run_reproduction → apply_file_changes → read_file → run_reproduction → run_full_tests → apply_file_changes → run_full_tests → finish | 1 |
| dev-016 | apply_file_changes → read_file → run_reproduction → run_full_tests → apply_file_changes → apply_file_changes → run_full_tests → finish | 1 |
| dev-016 | apply_file_changes → read_file → run_reproduction → run_full_tests → apply_file_changes → read_file → run_full_tests → finish | 2 |
| dev-016 | apply_file_changes → run_reproduction → run_full_tests → apply_file_changes → read_file → run_full_tests → finish | 1 |
| dev-016 | apply_file_changes → run_reproduction → run_full_tests → apply_file_changes → run_full_tests → finish | 1 |

### Matched-task resource ratios and success deltas

Ratios use mean per-attempt resources on matched task domains only;
Missing telemetry or zero denominators produce null. Deltas are percentage points.

| Comparison | Domain | Tokens | Cost | Model calls | Duration | Success delta (pp) |
| --- | --- | --- | --- | --- | --- | --- |
| S1 / S0 | dev-011 | 0.734697088906373 | 0.42486928847465333 | 1 | 0.5170401050860526 | 100 |
| S1 / S0 | dev-012 | 1.2490594431903688 | 1.1286581998895637 | 1 | 1.3523380706856831 | 0 |
| S1 / S0 | dev-013 | 1.9115927072583419 | 1.9134169884169885 | 1 | 1.2142358056049225 | 100 |
| S1 / S0 | dev-014 | 1.835016111707841 | 1.6939518682710577 | 1 | 1.1158049948461426 | 0 |
| S1 / S0 | dev-011, dev-012, dev-013, dev-014 | 1.4081495363029168 | 1.1121977069081799 | 1 | 0.9760923327891832 | 50 |
| S2 / S0 | dev-011 | 1.8539732494099135 | 1.4789724937485793 | 2 | 1.314671022558705 | 100 |
| S2 / S0 | dev-012 | 2.2633559066967646 | 1.7643290999447818 | 2 | 1.6077885253077762 | 0 |
| S2 / S0 | dev-013 | 3.0743034055727554 | 3.0533783783783783 | 2 | 2.3385337040701404 | 20 |
| S2 / S0 | dev-014 | 2.3800214822771215 | 2.125870804306523 | 2 | 1.498169847661999 | 0 |
| S2 / S0 | dev-015 | 3.109787786920745 | 3.4397502903600463 | 2 | 2.244162585012106 | 100 |
| S2 / S0 | dev-016 | 2.9347006129184345 | 2.6956214689265536 | 2 | 1.7667033389443025 | 100 |
| S2 / S0 | dev-011, dev-012, dev-013, dev-014, dev-015, dev-016 | 2.5806005864311956 | 2.2825102732319227 | 2 | 1.7687559613775046 | 53.333333333333336 |
| Agent / S0 | dev-011 | 8.520692368214005 | 2.684300977494885 | 7 | 1.7992776061483533 | 100 |
| Agent / S0 | dev-012 | 8.90845247052922 | 4.395091109884042 | 4.8 | 2.5421447446508245 | 0 |
| Agent / S0 | dev-013 | 10.17406260749914 | 5.687397683397683 | 6.2 | 2.7538181126138306 | 100 |
| Agent / S0 | dev-014 | 8.862943071965628 | 4.96786573780874 | 5 | 2.5494556540318216 | 0 |
| Agent / S0 | dev-015 | 18.235816370723256 | 12.916591173054588 | 7.8 | 4.706316258457407 | 100 |
| Agent / S0 | dev-016 | 16.707449316360208 | 10.11545197740113 | 7.4 | 3.7670092837466496 | 100 |
| Agent / S0 | dev-011, dev-012, dev-013, dev-014, dev-015, dev-016 | 11.632974958713895 | 5.94687405378127 | 6.366666666666666 | 2.837358902224828 | 66.66666666666667 |
| Agent / S2 | dev-011 | 4.595909013749788 | 1.814976944359053 | 3.5 | 1.3686143341369714 | 0 |
| Agent / S2 | dev-012 | 3.9359485815602837 | 2.4910835002503755 | 2.4 | 1.5811437291880077 | 0 |
| Agent / S2 | dev-013 | 3.3093879377867292 | 1.8626573515000158 | 3.1 | 1.177583247066699 | 80 |
| Agent / S2 | dev-014 | 3.723892048018774 | 2.336861547627914 | 2.5 | 1.7017133658179207 | 0 |
| Agent / S2 | dev-015 | 5.8640066847712555 | 3.755095597855907 | 3.9 | 2.0971369409191087 | 0 |
| Agent / S2 | dev-016 | 5.693067716282433 | 3.7525491223473932 | 3.7 | 2.1322251453929066 | 0 |
| Agent / S2 | dev-011, dev-012, dev-013, dev-014, dev-015, dev-016 | 4.507855659601144 | 2.6054095455880635 | 3.183333333333333 | 1.6041551034632822 | 13.333333333333334 |

### Findings

On dev-011, S0 succeeded 0/5 (0.0%); S1 succeeded 5/5 (100.0%); S2 succeeded 5/5 (100.0%); Agent succeeded 5/5 (100.0%).
On dev-012, S0 succeeded 5/5 (100.0%); S1 succeeded 5/5 (100.0%); S2 succeeded 5/5 (100.0%); Agent succeeded 5/5 (100.0%).
On dev-013, S0 succeeded 0/5 (0.0%); S1 succeeded 5/5 (100.0%); S2 succeeded 1/5 (20.0%); Agent succeeded 5/5 (100.0%).
S2 functional passes: 5/5; 4 final states failed lint. These remain evaluator failures.
On dev-014, S0 succeeded 5/5 (100.0%); S1 succeeded 5/5 (100.0%); S2 succeeded 5/5 (100.0%); Agent succeeded 5/5 (100.0%).
On dev-015, S0 succeeded 0/5 (0.0%); S2 succeeded 5/5 (100.0%); Agent succeeded 5/5 (100.0%).
On dev-016, S0 succeeded 0/5 (0.0%); S2 succeeded 5/5 (100.0%); Agent succeeded 5/5 (100.0%).

### Positive/negative controls

#### dev-011 versus dev-012

dev-011 (context-acquisition, positive): S0 0/5 (0.0%); S1 5/5 (100.0%); S2 5/5 (100.0%); Agent 5/5 (100.0%); S2 first shadow passed 0/5; Agent first shadow passed 5/5.
Fixed evidence coincided with more primary successes; this is consistent with useful information, not proof of causality.
Resource ratios S1 / S0: tokens 0.734697088906373, cost 0.42486928847465333, model calls 1, duration 0.5170401050860526.
Resource ratios S2 / S0: tokens 1.8539732494099135, cost 1.4789724937485793, model calls 2, duration 1.314671022558705.
Resource ratios Agent / S0: tokens 8.520692368214005, cost 2.684300977494885, model calls 7, duration 1.7992776061483533.

dev-012 (context-acquisition, negative): S0 5/5 (100.0%); S1 5/5 (100.0%); S2 5/5 (100.0%); Agent 5/5 (100.0%); S2 first shadow passed 5/5; Agent first shadow passed 5/5.
S0 already passed all repetitions; extra fixed evidence did not increase the primary outcome.
Resource ratios S1 / S0: tokens 1.2490594431903688, cost 1.1286581998895637, model calls 1, duration 1.3523380706856831.
Resource ratios S2 / S0: tokens 2.2633559066967646, cost 1.7643290999447818, model calls 2, duration 1.6077885253077762.
Resource ratios Agent / S0: tokens 8.90845247052922, cost 4.395091109884042, model calls 4.8, duration 2.5421447446508245.

#### dev-013 versus dev-014

dev-013 (runtime-diagnostic, positive): S0 0/5 (0.0%); S1 5/5 (100.0%); S2 1/5 (20.0%); Agent 5/5 (100.0%); S2 first shadow passed 0/5; Agent first shadow passed 5/5.
Fixed evidence coincided with more primary successes; this is consistent with useful information, not proof of causality.
Resource ratios S1 / S0: tokens 1.9115927072583419, cost 1.9134169884169885, model calls 1, duration 1.2142358056049225.
Resource ratios S2 / S0: tokens 3.0743034055727554, cost 3.0533783783783783, model calls 2, duration 2.3385337040701404.
Resource ratios Agent / S0: tokens 10.17406260749914, cost 5.687397683397683, model calls 6.2, duration 2.7538181126138306.

dev-014 (runtime-diagnostic, negative): S0 5/5 (100.0%); S1 5/5 (100.0%); S2 5/5 (100.0%); Agent 5/5 (100.0%); S2 first shadow passed 5/5; Agent first shadow passed 5/5.
S0 already passed all repetitions; extra fixed evidence did not increase the primary outcome.
Resource ratios S1 / S0: tokens 1.835016111707841, cost 1.6939518682710577, model calls 1, duration 1.1158049948461426.
Resource ratios S2 / S0: tokens 2.3800214822771215, cost 2.125870804306523, model calls 2, duration 1.498169847661999.
Resource ratios Agent / S0: tokens 8.862943071965628, cost 4.96786573780874, model calls 5, duration 2.5494556540318216.

### Progressive feedback

dev-015: S0 0/5 (0.0%); S2 5/5 (100.0%); Agent 5/5 (100.0%). S2 first shadows passed 0/5; post-feedback functional recoveries: 5.
Stored Agent occurrences: {"context_refinement_iteration": 0, "feedback_responsive_iteration": 5, "none": 0, "tool_assisted_one_patch": 0}.
Agent/S2 ratios: tokens 5.8640066847712555, cost 3.755095597855907, model calls 3.9.
Functional improvement followed post-attempt feedback; this observed transition does not establish necessity.
S2 and Agent both passed all repetitions; these data do not establish that adaptive autonomous tool selection was necessary.

dev-016: S0 0/5 (0.0%); S2 5/5 (100.0%); Agent 5/5 (100.0%). S2 first shadows passed 0/5; post-feedback functional recoveries: 5.
Stored Agent occurrences: {"context_refinement_iteration": 0, "feedback_responsive_iteration": 5, "none": 0, "tool_assisted_one_patch": 0}.
Agent/S2 ratios: tokens 5.693067716282433, cost 3.7525491223473932, model calls 3.7.
Functional improvement followed post-attempt feedback; this observed transition does not establish necessity.
S2 and Agent both passed all repetitions; these data do not establish that adaptive autonomous tool selection was necessary.

Agent used 4.51× as many tokens per attempt as S2 across matched DEV-v3 tasks.

## Validation notes

dev-v3: missing telemetry for fixed_evidence_duration_seconds
