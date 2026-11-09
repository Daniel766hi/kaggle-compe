# Verification of model inputs (November 2026)

The seven inputs flagged as unverified in the preliminary run were checked against published sources.
Several checks changed the model. The cloud session could not open Indonesian news sites or bps.go.id
directly, so some figures were confirmed from search-engine extracts of the sources listed below.
The **Residual check** column says what to confirm by opening the source yourself.

| # | Input | Before | After | Source | Residual check |
|---|---|---|---|---|---|
| 1 | Household egg elasticity | −0.7 | **−0.669** | Khoiriyah, Forgenie, Sookhai & Saputro (2024), *Int. J. Food Agric. Econ.* 12(3), 171–188: QUAIDS on SUSENAS 2021, DI Yogyakarta (eggs −0.669, poultry −1.581, beef −2.661, fish −2.229, milk −1.541) | Confirm in the full text whether these are uncompensated (Marshallian) elasticities |
| 2 | Household chicken elasticity | −1.55 | **−1.581** | as above | as above |
| 3 | Initial egg production | 121,950 t/wk | **121,640 t/wk** | BPS 2024 (preliminary): 6,342,705 t laying-hen eggs (East Java 2,016,324 t; Central Java 809,399 t; West Java 730,255 t), reported by GoodStats; 2023: 6,117,905 t | Open the BPS table "Produksi Telur Ayam Petelur menurut Provinsi" and record URL and access date |
| 4 | Initial chicken production | 73,660 t/wk | **73,565 t/wk** | BPS 2024 (preliminary, updated 28 Apr 2025): 3,835,917 t broiler meat (West Java 857,577 t), reported by Kontan | Same, table "Produksi Daging Ayam Ras Pedaging menurut Provinsi" |
| 5 | Portions per beneficiary | 5 | 5 (confirmed) | Meals on school days only, five a week, from early 2026 (previously six) — Menko Pangan and Finance Minister statements, March 2026 | Affects cost per portion only |
| 6 | SPPG counts | Wikipedia rows | **Replaced with BGN figures reported in the press** | See `mbg_rollout_observed.csv` (each row has its URL). Wikipedia rows removed; 10,012 (29 Sep 2025, Wikipedia) replaced by BGN's 9,615 (28 Sep 2025) | Replace remaining press reports with BGN releases where available |
| 7 | Menu quantities | constant 0.15 kg egg, 0.18 kg chicken | **Egg: time-varying; chicken: deep uncertainty** | See below | Confirm the national scope and duration of the June 2026 egg rule |

## Changes to the model structure that verification required

1. **Beneficiaries per kitchen fell in 2026.** Reported beneficiaries ÷ operational SPPG were about 2,700–3,200
   until February 2026, but about 2,000 in September 2026 (53–57 million beneficiaries, 27,485 SPPG).
   The constant 2,850 overstated programme demand in late 2026 by about 40%. The model now uses the observed
   ratio up to 30 September 2026 and an uncertain future level (1,900–2,900; BGN cap of 2,500 portions per
   SPPG, 3,000 with certified cooks, Keputusan Kepala BGN 244/2025).
2. **Egg menu.** About two egg dishes a week (BGN head, April 2025: 480 kt/yr for 82.9 million beneficiaries,
   assuming two egg dishes a week); at least three a week from 8 June 2026 under an agreement between BGN and farmer
   groups, described as temporary. Modelled as serving size (0.05–0.065 kg) × servings per week (2, then 2–4).
   The temporary substitution of chicken eggs requested by the President in November 2025 is not modelled
   (its size and duration were not reported) and is stated as a limitation.
3. **Chicken menu.** No published menu specification; official estimates conflict (Agriculture Minister,
   Nov 2025: 1.1 Mt/yr additional chicken; Bapanas: 222.7 kt for SPPG in 2025; GOPAN: chicken oversupplied by
   about 34 kt/month in Nov 2025). Kept as a deep uncertainty, 0.08–0.26 kg per beneficiary per week.
4. **School holidays.** Meals pause during school holidays. Before June 2026 pregnant and breastfeeding
   mothers and toddlers (about 20% of portions) continued to receive meals; BGN circular SE 12/2026
   (June 2026) stopped distribution to all groups on school holidays, public holidays and weekends. The
   Agriculture Minister asked companies to absorb farmers' eggs and chicken while MBG paused (June 2026) and
   attributed the July 2026 price rise to MBG demand after schools reopened. Modelled with an approximate
   national holiday calendar (23 Jun–13 Jul, 20 Dec–3 Jan, one week either side of Idul Fitri).

## Sources (accessed 9 Nov 2026)

- Kontan, BPS broiler production 2024: https://nasional.kontan.co.id/news/data-produksi-daging-ayam-ras-pedaging-di-indonesia-2024-tertinggi-jawa-barat
- GoodStats, BPS egg production 2024: https://goodstats.id/article/produksi-telur-nasional-naik-3-68-persen-jawa-timur-penyumbang-terbesarproduksi-telur-ayam-petelur-di-indonesia-mencapai-6342705-ton-pada-tahun-2024-angka-ini-naik-3-68-persen-dibandingk-yHIST
- Khoiriyah et al. (2024): https://doaj.org/article/5c2aa59207044dd88eb6e0c4159b087a
- Bisnis, BGN head on egg demand (8 Apr 2025): https://ekonomi.bisnis.com/read/20250408/12/1867518/kepala-bgn-wanti-wanti-ri-bisa-krisis-telur-buat-penuhi-mbg
- Republika, President asks to replace chicken eggs temporarily (21 Nov 2025): https://news.republika.co.id/berita/t61xeu409/prabowo-minta-sementara-telur-ayam-di-menu-mbg-diganti-telur-puyuh
- Detik, egg menu at least three times a week (June 2026): https://finance.detik.com/berita-ekonomi-bisnis/d-8522633/menu-telur-program-mbg-minimal-3-kali-seminggu-imbas-harga-anjlok
- Avinews, BGN and farmers agree minimum three egg menus a week: https://avinews.com/id/komitmen-bgn-dan-peternak-menu-telur-di-mbg-minimal-3-kali-seminggu/
- CNN Indonesia, SE 12/2026, holiday stop for all groups (19 Jun 2026): https://www.cnnindonesia.com/ekonomi/20260619124748-92-1370802/mbg-bumil-busui-dan-balita-ikut-disetop-sementara-saat-libur-sekolah
- CNN Indonesia, Minister asks companies to absorb eggs and chicken while MBG pauses (17 Jun 2026): https://www.cnnindonesia.com/ekonomi/20260617180357-92-1370127/mbg-libur-amran-minta-perusahaan-serap-telur-daging-ayam-peternak
- Okezone, prices rise after holidays, Minister cites MBG (27 Jul 2026): https://economy.okezone.com/read/2026/07/27/320/3232582/harga-ayam-dan-telur-naik-mentan-sebut-efek-mbg
- Detik, SPPG capacity cap (Oct 2025): https://finance.detik.com/berita-ekonomi-bisnis/d-8185320/bgn-batasi-dapur-mbg-maksimal-siapkan-3-000-porsi-per-hari
- Kontan, GOPAN on chicken oversupply: https://industri.kontan.co.id/news/produksi-ditambah-gopan-pasokan-ayam-masih-lebih-untuk-program-mbg
- Bisnis, Kementan on egg and chicken prices (19 Nov 2025): https://ekonomi.bisnis.com/read/20251119/12/1930149/kementan-pastikan-harga-telur-dan-ayam-stabil-pasokan-untuk-program-mbg-aman
- Kemenkopangan / Menko Pangan, school-day schedule: https://nu.or.id/nasional/p2g-soroti-skema-mbg-5-hari-harus-disesuaikan-dengan-kalender-sekolah-XfnEL
- SPPG counts: URLs in `mbg_rollout_observed.csv`
