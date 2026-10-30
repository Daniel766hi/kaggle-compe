# NeurIPS 2026 Smart Buildings: panduan mulai

Kompetisi: https://www.kaggle.com/competitions/neurips-2026-smart-buildings
Starter kit: https://github.com/smart-buildings-2026/starter-kit (commit `95cea5b`, dibaca 28 Okt 2026)

## Fakta resmi (halaman Kaggle, 28 Okt 2026)

| Hal | Nilai |
|---|---|
| Paper ronde 1 (OpenReview) | 13 Nov 2026 |
| Entry dan team merger | 3 Jan 2027 |
| Final leaderboard dan paper final | 15 Jan 2027 |
| Batas submit | 5/hari, pilih 2 final |
| Format submit | Notebook Kaggle, CPU atau GPU maks. 9 jam, tanpa internet |
| Hadiah paper ronde 1 | US$1.000 / 750 / 500, peringkat 4–14 masing-masing US$250 |
| Hadiah paper final | US$3.000 / 1.750 / 750, peringkat 4–12 masing-masing US$500 |
| Hadiah leaderboard | US$25.000 untuk 8 juara |
| Tempat paper | https://openreview.net/group?id=NeurIPS.cc/2026/Workshop/SB26_Challenge |

Format dan batas halaman paper belum pasti, karena openreview.net tidak bisa dibuka dari sesi ini.

## Tugas

Satu policy mengendalikan HVAC gedung yang belum pernah dilihat: on/off AHU dan pompa,
suhu suplai udara, static pressure, resirkulasi, suhu dan tekanan air panas, serta damper
dan reheat per zona. Reward per langkah 5 menit:
`0.6 × kenyamanan − 0.2 × biaya energi − 0.2 × emisi`. Reward selalu ≤ 0.
Skor = rata-rata |reward per langkah| di semua skenario. Makin kecil makin baik.
Satu episode berisi 8.640 langkah (30 hari).

Evaluasi lokal memakai 6 gedung × 5 cuaca = 30 skenario. Penilaian Kaggle memakai gedung
held-out dari generator yang sama.

## Skor baseline (dihitung dari `baseline_returns.json`)

| Policy | Skor 30 skenario latih |
|---|---|
| `bang_bang` | 0.2252 |
| `fixed_setpoint` | 0.0659 |
| `pid` | 0.0674 |
| `pid_water` | 0.0541 |
| Baseline terbaik per skenario (oracle) | 0.0473 |

Kerugian terbesar ada di cuaca ekstrem. Rata-rata baseline terbaik: Phoenix 0.077,
Fairbanks 0.068, Denver 0.037, Atlanta 0.029, Singapore 0.025.

Leaderboard publik Kaggle (28 Okt): peringkat 1 di 0.00514, peringkat 12 di 0.00605,
dari 410 tim. Angka ini sekitar 10 kali lebih kecil daripada skor baseline lokal. Belum pasti
apakah skenario held-out memang lebih ringan atau skalanya berbeda. Ini perlu dicek dengan
men-submit satu baseline (misalnya `pid_water`) lebih dulu.

## Menjalankan

Butuh Python 3.12 atau lebih baru dan sekitar 1 GB disk. Cukup CPU.

```bash
git clone https://github.com/smart-buildings-2026/starter-kit.git ../smart-buildings-starter-kit
cd ../smart-buildings-starter-kit
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .

# Tes cepat: 1 hari, 1 skenario (tidak sebanding dengan skor baseline)
python -m smart_buildings.evaluate --policies transfer pid_water \
    --buildings building_train_1 --weathers fairbanks_1 --steps 288

# Skor lengkap: 30 skenario × 30 hari
python -m smart_buildings.evaluate --policies pid_water
python score_leaderboard.py smart_buildings/results --policy pid_water --expect 30
```

Policy Anda ditulis di `smart_buildings/baselines/transfer_policy.py` (kelas `TransferPolicy`,
dengan method `__init__(building_meta_data, action_spec)` dan `get_action(obs)`).
Ambil indeks aksi dari `building_meta_data`, jangan di-hardcode.

## Notebook submit

Notebook `notebooks/smart_buildings_submission.ipynb` (sumbernya `.py`, format percent) mengikuti
notebook resmi "TransferPolicy Notebook" dari tab Code. Paket `smart_buildings` beserta 30
skenario latih sudah ada di data kompetisi, jadi notebook tidak butuh internet.

- `MyPolicy` = baseline `pid_water`. Perubahan Anda ditulis di kelas ini.
- `SubmissionPolicy` membungkus `MyPolicy` untuk server inference, lalu memotong (clip) aksi
  ke batas ruang aksi.
- Sel penilaian lokal (`LOCAL_EVAL` = `smoke` / `scenario` / `full`) dilewati saat rerun tersembunyi.
- Cara pakai: Kaggle → New Notebook → File → Import Notebook → pilih `.ipynb`. Lalu Add Input
  data kompetisi, Internet off, Save Version, dan submit versi itu.

### Hasil submit pertama

`pid_water` tanpa perubahan mendapat skor publik **0.0052** (dilaporkan 30 Okt 2026).
Leaderboard saat itu: peringkat 1 di 0.00470 dan peringkat 20 di 0.00627, dari 410 tim.
Artinya skenario uji tersembunyi jauh lebih ringan daripada skenario latih (`pid_water` mendapat
0.0541 di skenario latih). Leaderboard publik hanya memakai 33% skenario uji.

### Notebook v2: ablation hemat waktu

`notebooks/smart_buildings_v2_ablation.ipynb` membandingkan 8 varian pada 5 skenario (satu per
stasiun cuaca) × 7 hari, dengan batas waktu `TIME_BUDGET_MIN`. Varian yang dibandingkan:
rantai baseline resmi (`pid` → `pid_worst` → `pid_econ` → `pid_prop` → `pid_water`),
`water_sensor` (`USE_SENSOR_BAND = True`, saklar yang ada di baseline tapi dimatikan),
`water_precond` (pita nyaman 1 jam sebelum jam kerja), dan gabungan keduanya.
Hasilnya ditulis ke `ablation_results.csv` dan `ablation_summary.csv`, termasuk rincian
kenyamanan, energi, dan karbon. Notebook yang sama bisa di-submit lewat `SUBMIT_VARIANT`.

## Peluang perbaikan (dari dokumentasi starter kit)

- AHU hanya bisa mendinginkan. Semua pemanas berasal dari reheat VAV lewat loop air panas.
  Saat udara luar di bawah −6.8 °C, setpoint suhu suplai udara tidak berpengaruh
  (31.5% jam di Fairbanks). Di cuaca dingin, kendali yang efektif adalah suhu air panas dan katup reheat.
- Penalti kenyamanan kuadratik tanpa batas, jadi satu zona yang terabaikan bisa merusak skor episode.
  Kendalikan berdasarkan zona terburuk, bukan rata-rata zona.
- Pakai jadwal okupansi dan flag "comfort mode soon" untuk pre-conditioning sebelum jam kerja.
- Untuk validasi held-out, buat gedung baru dengan `run_floor_generator` dan `run_scenario_generator`,
  supaya policy tidak overfit ke 30 skenario latih.

## Rencana sampai paper 13 Nov

1. Join kompetisi di Kaggle dan terima rules (harus dilakukan pemilik akun).
2. Jalankan keempat baseline secara lokal, lalu submit `pid_water` sekali untuk memastikan skala skor Kaggle.
3. Kembangkan policy dari `pid_water`: kendali zona terburuk, reheat dan reset air panas untuk cuaca dingin,
   pre-cooling untuk cuaca panas, dan pre-conditioning berbasis jadwal.
   Ukur setiap perubahan per skenario (ablation).
4. Validasi di gedung hasil generator, lalu submit versi terbaik.
5. Tulis paper: masalah, metode, tabel ablation per iklim, generalisasi lintas gedung, dan keterbatasan.
