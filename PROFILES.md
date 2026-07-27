# Device profiles

Rainbow Energy Modbus Client loads inverter register maps from YAML. Each profile describes one
device model and how to decode its Modbus registers into named measurements.

## Where profiles live

| Location | Purpose |
|----------|---------|
| [`src/rainbow_energy_modbus_client/data/`](src/rainbow_energy_modbus_client/data/) | Production profiles shipped with the package. Must load and be fully supported. |
| [`profiles/draft/`](profiles/draft/) | Work-in-progress maps for gap analysis. Not packaged. |

Load a packaged profile in code with `load_packaged_profile("sunsynk_8k_sg05lp1")`.
Use `load_profile(path)` for a custom YAML file on disk.

Validate a profile (schema, overlaps, and decode support):

```bash
rainbow-energy-modbus-client check-profile sunsynk_8k_sg05lp1
rainbow-energy-modbus-client check-profile path/to/profile.yaml
```

During development you can also use:

```bash
make check-profile PROFILE=src/rainbow_energy_modbus_client/data/sunsynk_8k_sg05lp1.yaml
```

Exit codes: `0` supported, `1` unsupported features, `2` load/schema error.

List packaged profile names:

```bash
rainbow-energy-modbus-client list-profiles
```

## Creating a new profile

1. Copy an existing production profile or start from a draft map.
2. Set top-level `manufacturer`, `model`, and `registers`.
3. Add one entry per named value (leaf Modbus register or math sensor).
4. Run `make check-profile PROFILE=...` until it exits `0`.
5. Place the file in `src/rainbow_energy_modbus_client/data/` when it is ready to ship (not `profiles/draft/`).

Keep **one clear meaning per address** (except disjoint `bitmask`s on the same
word). Do not ship conflicting aliases for the same register.

## Top-level fields

```yaml
manufacturer: Sunsynk
model: SYNK-8K-SG05LP1
registers:
  - key: battery_soc
    # ...
```

| Field | Required | Meaning |
|-------|----------|---------|
| `manufacturer` | yes | Non-empty string |
| `model` | yes | Non-empty string |
| `registers` | yes | Non-empty list of register definitions |

Keys are unique case-insensitively (`Battery_SOC` and `battery_soc` conflict).

## Register fields (common)

Every register needs:

| Field | Meaning |
|-------|---------|
| `key` | Stable machine id (snake_case recommended) |
| `name` | Human-readable label |
| `data_type` | How to interpret the value (see below) |
| `unit` | Engineering unit, or `""` when none |
| `access` | `read` or `write` |

### Leaf Modbus registers

Also require `address`, `function`, and `scale`:

| Field | Meaning |
|-------|---------|
| `address` | First Modbus address (`0`–`65535`) |
| `function` | `holding` or `input` |
| `scale` | Non-zero multiplier after typed decode (`value = raw * scale`) |
| `count` | Word count (fixed for most types; required for `string`, `fault`, and `datetime`) |
| `word_order` | `big` or `little` (required for 32-bit types) |
| `offset` | Optional; applied after scale: `(raw * scale) - offset` |
| `bitmask` | Optional; AND each word before typed decode |
| `options` | Optional; map integer → label string |
| `binary` | Optional; `true` → nonzero (after mask) is `True` |
| `bits` | Required for `fault`; map 1-based bit index → label string |

Decode order for leaf registers: **bitmask → typed raw → options or binary or
(scale then offset)**.

Encode for writes inverts that path: **options/binary/time/datetime or
(offset then inverse scale) → words**. Bitmasked writes read the current
holding word, clear the masked bits, OR in the encoded contribution, then
write the full word. Only `access: write` holding leaf registers are
writable; math and `access: read` keys are rejected.

### Math registers

Use `data_type: math`. Do **not** set `address`, `function`, `scale`, or
`count`. Provide `sources` instead (see [Math](#math)).

## Data types

### `uint16` / `int16`

One register word. `count` must be `1`. No `word_order`.

- `uint16`: unsigned `0`–`65535`
- `int16`: two’s complement signed

```yaml
  - key: battery_soc
    name: Battery SOC
    address: 184
    function: holding
    data_type: uint16
    scale: 1
    unit: "%"
    access: read
```

### `uint32` / `int32` / `float32`

Two register words. Require `count: 2` and `word_order: big|little`.
No `bitmask` (masking multi-word values is not supported).

- `big`: first word is high
- `little`: first word is low
- `float32`: IEEE-754; non-finite values raise a decode error

```yaml
  - key: total_pv_energy
    name: Total PV Energy
    address: 96
    function: holding
    data_type: uint32
    count: 2
    word_order: big
    scale: 0.1
    unit: kWh
    access: read
```

### `string`

ASCII packed two characters per word. Require `count` (1–125) and `scale: 1`.
Trailing `\x00` bytes are stripped. No `bitmask`, `offset`, `options`,
`binary`, or `word_order`.

```yaml
  - key: serial
    name: Serial
    address: 3
    function: holding
    data_type: string
    count: 5
    scale: 1
    unit: ""
    access: read
```

### `protocol`

One word decoded as a version string `"major.minor"` from high/low bytes
(`0x0105` → `"1.5"`). Require `scale: 1`. No `bitmask`, `offset`, `options`,
or `binary`.

```yaml
  - key: protocol
    name: Protocol
    address: 2
    function: holding
    data_type: protocol
    scale: 1
    unit: ""
    access: read
```

### `time`

One word packed as `hours * 100 + minutes` (SunSynk style), decoded
as `"H:MM"` (`830` → `"8:30"`). Hours wrap with `% 24`. Minutes `>= 60` raise a
decode error. Require `scale: 1`. No `bitmask`, `offset`, `options`, or
`binary`.

```yaml
  - key: prog1_time
    name: Prog1 Time
    address: 250
    function: holding
    data_type: time
    scale: 1
    unit: ""
    access: write
```

### `datetime`

Three words packing the inverter system clock (SunSynk system-time
layout). Year is stored as an offset from 2000 in the high byte of the first
word. Decoded as `"YYYY-MM-DD H:MM:SS"` (hour is not zero-padded). Require
`count: 3` and `scale: 1`. Out-of-range month/day/hour/minute/second raise a
decode error. No `bitmask`, `offset`, `options`, `binary`, `bits`, or
`word_order`.

```yaml
  - key: date_time
    name: Date Time
    address: 22
    function: holding
    data_type: datetime
    count: 3
    scale: 1
    unit: ""
    access: write
```

### `fault`

Multi-word bitfield of inverter fault flags. Require `count` (1–125),
`scale: 1`, and `bits` (map of 1-based bit index → label). Bit 0 of the first
word is **F01**. Set bits become `"F{nn}"` plus the label when known; unlabeled
set bits still appear as bare `"F{nn}"`. Join with `", "`; clear registers
decode to `""`. No `bitmask`, `offset`, `options`, `binary`, or `word_order`.

```yaml
  - key: fault
    name: Fault
    address: 103
    function: holding
    data_type: fault
    count: 4
    scale: 1
    unit: ""
    access: read
    bits:
      13: Working mode change
      18: AC over current
```

### `math`

Derived value from other profile keys (engineering values, after those keys
are decoded). No Modbus address of its own.

```yaml
  - key: essential_power
    name: Essential Power
    data_type: math
    unit: W
    access: read
    sources:
      - key: inverter_power
        factor: 1
      - key: grid_power
        factor: 1
      - key: aux_power
        factor: -1
```

| Field | Meaning |
|-------|---------|
| `sources` | Non-empty list of `{key, factor}`; `factor` must be non-zero |
| `no_negative` | Optional; clamp result to `0` if negative |
| `absolute` | Optional; use absolute value of the sum |

Rules:

- Each source `key` must exist and must not itself be `math` (no nesting yet).
- Result: `sum(source_value * factor)`, then `absolute`, then `no_negative`.
- When reading a math key, Rainbow Energy Modbus Client expands sources, batches leaf Modbus reads,
  then combines. Requesting a math key and a source key together reuses one
  leaf read.

## Optional decode modifiers

### `offset`

After scale: `(raw * scale) - offset`. Useful for temperatures encoded with a
bias (for example `offset: 100`). Not allowed with `string`, `fault`,
`datetime`, `options`, `binary`, or `math`.

### `bitmask`

`raw = word & bitmask` before typed decode. Only on single-word numeric types
(`uint16` / `int16` / `protocol` forbids it). Several registers may share an
address if their masks do **not** overlap.

```yaml
  - key: prog1_charge
    address: 274
    bitmask: 0x03
    # ...
  - key: prog1_mode
    address: 274
    bitmask: 0x1C
    # ...
```

### `options`

Map the integer value (after bitmask) to a string label. Require `scale: 1`.
Unknown values raise a decode error (Rainbow Energy Modbus Client does not return `"unknown N"`
strings). Not allowed with `offset`, `binary`, `string`, or `math`.

Use this for discrete codes such as SD status (`1000` → fault, `2000` → ok).

```yaml
    options:
      0: No Grid or Gen
      1: Allow Grid
      2: Allow Gen
      3: Allow Grid & Gen
```

### `binary`

Set `binary: true`. After bitmask, nonzero → `True`, zero → `False`.
Require `scale: 1`. Not allowed with `offset` or `options`.

There is no separate `on` value yet: any nonzero masked value is on.

## Address overlap rules

- Two registers with the same `function` and overlapping address ranges are
  rejected unless both use `bitmask` and the masks are disjoint.
- Full-word (no mask) claims conflict with any other claim on that word.
- `math` entries do not occupy addresses.

## Measurement values

Decoded `Measurement.value` types by feature:

| Feature | Python type |
|---------|-------------|
| Numeric leaf | `int` or `float` |
| `string` / `protocol` / `time` / `datetime` / `options` / `fault` | `str` |
| `binary` | `bool` |
| `math` | `int` or `float` |

## Not supported yet

These appear in some community maps but are not expressible in Rainbow Energy Modbus Client today:

- Non-contiguous multi-register values (for example energy across gaps)
- Nested math sources
- Explicit binary `on` values (only nonzero-after-mask)

Use `profiles/draft/` while exploring those, and `make check-profile` to list
gaps.

## Minimal example

```yaml
manufacturer: Example Energy
model: Example 8K
registers:
  - key: battery_soc
    name: Battery SOC
    address: 184
    function: holding
    data_type: uint16
    scale: 1
    unit: "%"
    access: read

  - key: grid_charge_enabled
    name: Grid Charge Enabled
    address: 232
    function: holding
    data_type: uint16
    bitmask: 0x1
    scale: 1
    unit: ""
    access: write
    binary: true
```
