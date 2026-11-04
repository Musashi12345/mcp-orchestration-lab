# Three-question comparison

Updated: 2026-10-27. This small study compares a graph plan (D1/D2) with a limited
Python plan (P1/P2), with execution reviews enabled for D2/P2. Each mode makes its own
fresh plan from the same question and its declared CSV. All modes share the agents,
tool gate, calculations, limits and independent answer checks.

The three questions cover an order total (Q01), cleaning followed by regional totals
(Q05), and a specified last-value forecast (Q10). This means twelve question/mode
results, not every question applied to every CSV.

## Results

| Mode | Latest answers passed | First attempts passed | Attempts counted | Model calls | Tokens | Recorded minutes |
|---|---|---|---|---|---|---|
| D1 | 3/3 | 3/3 | 3 | 20 | 398,162 | 29.91 |
| D2 | 3/3 | 2/3 | 4 | 25 | 547,927 | 37.15 |
| P1 | 3/3 | 3/3 | 3 | 20 | 397,568 | 30.05 |
| P2 | 3/3 | 3/3 | 3 | 24 | 533,091 | 36.66 |

Q05 D2 passed on its second attempt using unchanged application code and settings.
Both attempts' time, calls and tokens are counted. The failed attempt stopped during
Main Task creation, before tool execution. It asked for tool information that this
early planning stage had not received. The successful retry does not repair that issue.

The main comparison contains thirteen attempts, 89 calls and 1,876,748 reported tokens.
Every current call has reported usage. All 34 historical attempts remain saved locally;
21 older attempts are outside this main comparison because the source/settings differ
or they were superseded. Eight older calls have unavailable token counts.

## What we observed

- D1 and P1 differed by 594 tokens, or 0.15%, across the three questions.
- D2 and P2 used 37.6% and 34.1% more tokens than their versions without reviews,
  including the D2 failed attempt. All eight completed reviews chose KEEP; no revised
  plan was accepted. Six reviews happened after all original jobs had finished.
- Planning used 67.4% of current tokens. Input accounted for 98.7% of tokens;
  repeated tool descriptions are one place to investigate further.
- Model-spacing waits occupied 84.5% of recorded application time. These times describe
  the configured application, rather than establishing which executor is faster.

These tasks used only Analysis, Cleaning and Prediction, with one or two jobs per plan.
The results show that the four paths can complete these known tasks. They do not
establish a general winner, a benefit from replanning, recovery from tool failures,
or performance on larger parallel plans. Q10 checks the requested simple forecast;
it does not demonstrate a better forecasting method. Trials on unseen data and repeated
runs are outside this small collection.

## Recorded controls and evidence

All main attempts use `configs/experiments/csv_gap90_300k.yaml`: `gpt-6.1-sol`, low
reasoning, a 300,000-observed-token guard, at most 32 model calls, a 30-minute run limit,
90-second model spacing, and the same two review thresholds after one and two finished
attempted jobs. A token guard is checked after responses; it is not a hard billing cap.

- Application source SHA-256: `bf965b2f11eb8f662a6a2839d7a936f2c27c48b41abfce747ac4deecfa881c3b`
- Dependency lock SHA-256: `0735e36daf5497abe2643c64347489f7699cef6a1549c3bd43b4952c2210e247`
- Loaded configuration SHA-256: `e3fc8e5261b573b7782e876613a4b86438d4b940c77ed972baf99977aa2a1db7`
- Suite SHA-256: `7609232468b6eca594015780e106c42475ecb5003283bc2d9072ace26f920cca`
- Grader SHA-256: `1e409c583bfe5cce2c437874e348e6600679a87e85e0a1a4b908b6ccbbf8e62d`

These are the recorded run identities. The configuration hash covers loaded settings,
including defaults; it is different from a hash of the YAML file's bytes.

The read-only audit checked PostgreSQL records, 144 registered file hashes, saved
requests/usage, and the thirteen current grades without changing the original evidence.
Detailed records remain under local `reports/comparison_2026-10-27/`, with original
run files and PostgreSQL records retained. User CSVs, credentials and raw run records
are excluded from Git. This summary contains aggregate results for the public repository.

See [research controls](../experiment_protocol.md), [evaluation commands](Running.md),
and [implementation limits](../limitations.md).
