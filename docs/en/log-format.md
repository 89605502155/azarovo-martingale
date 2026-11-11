# Log format

[Русская версия](../ru/log-format.md)

A monitoring log is a CSV file with a header line and one row per sample of one VM.
Samples of several VMs can share the file.

| Column | Required | Content |
|---|---|---|
| `time` | yes | time of the sample, in seconds (Unix time is fine) |
| `vm` | yes | identifier of the VM |
| `used_mb` | yes | memory used by the VM, MiB |
| `free_mb` | recommended | free reserve `R` of the VM, MiB; without it give `--reserve` |
| `phase` | no | `growth` on the samples of a growth period; any other value is calm use |

Example:

```text
time,vm,used_mb,free_mb,phase
0,vm-01,2048.0,1352.0,calm
1,vm-01,2049.7,1350.3,calm
2,vm-01,2048.4,1351.6,calm
```

Rules.

* The header names are case-insensitive; extra columns are ignored.
* The delimiter (comma, semicolon or tab) is detected; you can set it with `--sep`.
* A decimal comma is accepted: `100,5` is 100.5.
* Samples are sorted by time for each VM. If two samples of one VM have the same
  time, the first one is kept and the others are counted as duplicates.
* Empty lines are skipped.

## Where the values come from

With libvirt, `virsh dommemstat <vm>` or `dom.memoryStats()` in libvirt-python give
`available`, `unused` and `usable` in kibibytes, when the balloon driver reports
them. A possible mapping is `used_mb = (available - usable) / 1024` and
`free_mb = usable / 1024`. The fields depend on the libvirt version and the driver,
so check them on your system.

## Phase labels

The `phase` column is needed for the false-alarm and delay figures. Record the
start and the end of a load in a controlled experiment, and mark the samples between
them as `growth`. Without the column, the analysis still checks A1, A2, the guarantee
(6), and the policies, but it does not count false alarms.
