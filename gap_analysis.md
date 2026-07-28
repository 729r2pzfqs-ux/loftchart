# LoftChart Iron Model Gap Analysis

**Date:** 2026-07-28
**Current state:** 394 models across 23 brands
**Candidates identified:** ~410 missing models (verified via web research)
**Projected total if all batches added:** ~800 models — inside the 750–1000 target

Research method: four parallel research passes (TaylorMade/Callaway, Titleist/Ping/Mizuno, mid-tier brands + PXG, new/JDM/DTC brands), each cross-checked against 2nd Swing used inventory, Callaway Pre-Owned, manufacturer archive/spec pages, Pitchmarks by-year lists, MyGolfSpy, GolfWRX, and Today's Golfer. Priority reflects estimated spec-search demand: **high** = current retail or dominant used-market volume; **medium** = steady spec-search demand; **low** = niche/vintage but findable.

Excluded throughout: wedges, putters, and single utility/driving irons (UDI, DHY, Crossover, U-series, 0317 X, etc.). Women's lines included only where genuinely searched (Kalea, Solaire, G Le).

---

## 1. Current inventory by brand

| Brand | Models | Biggest gaps found |
|---|---|---|
| Mizuno | 58 | Hot Metal Pro/HL variants, JPX 850/900 Tour, JPX EZ, MX line, T-Zoid, vintage blades |
| Titleist | 50 | 2021 T-series gen, 704/735/755/775, ZB/ZM, DCI B-variants, AP1 2008 |
| TaylorMade | 48 | **P770 2020 (missing generation)**, Tour Preferred 2011/2014, RAC era, 90s Burner |
| Ping | 47 | i (2015), i3+, Eye 2 Plus, Rapture, Karsten 2014, women's lines |
| Callaway | 43 | **Apex Pro 2014/16/19**, Rogue X, X Forged gens, X-Tour models, Diablo, RAZR variants |
| Cobra | 24 | Air-X, F-Max, King Max 2026, S9/FP era, 90s King Cobra |
| Srixon | 17 | Z 965, I-series (302/403/506/701), Z-TX |
| Wilson | 14 | Launch Pad, D9 Forged, D100–D350, C200, Di series |
| Cleveland | 11 | Launcher UHX, HALO XL, 588 irons, CG1–CG Black, TA series |
| PXG | 11 | Gen1–Gen3, XP Gen4/6/7, 0211 DC/XCOR2 |
| Honma | 9 | TW737, TW727, T//World-X, GS, Beres |
| Miura | 8 | MB-001 Baby Blade, CB-57, CB-1008, MB-5005, IC-601, PP-9003 |
| XXIO | 8 | Gens 9/10/Eleven, X 2020, Prime 9–11 |
| Nike | 7 | Vapor Fly Pro, VR-S line, Slingshot variants, Pro Combo |
| Ben Hogan | 7 | Apex Edge/Plus (pre-Callaway), Apex 1972, Radial |
| Adams | 6 | Idea 2024 revival, a1/a2/a3, Pro Forged/Gold/Black, MB2/CB2 |
| Bridgestone | 5 | 220 MB, 222 CB+, X-CBP/X-Blade, JGR, J15/J33/J36/J38 |
| Tour Edge | 5 | Hot Launch 521–523, Exotics 721, EXS |
| Sub 70 | 3 | 639 CB/MB, 699 originals, 799 |
| New Level | 3 | 902-PD, 902 Forged, 1031 |
| Takomo | 8 | None — complete |
| Tommy Armour | 1 | 855s, 845 reissues (2019/Max/+), Atomic |
| Kirkland | 1 | None — complete |

**New brands recommended for addition** (Batch 5 onward): Edel, Fourteen, Maltby, Haywood, Yonex, Epon, Vega, Proto-Concept, Stix, Wishon, Top Flite.

---

## 2. Data-quality flags on EXISTING entries (fix before/while adding)

1. **TaylorMade `tp-cb-irons` / `tp-mb-irons`** — ambiguous between the 2011 and 2014 Tour Preferred generations. Check which gen the stored specs match; both gens are candidates below, so the existing entries should become versioned.
2. **PXG `0317-t-irons`** — PXG's milled blade line is named **0317 ST** (2022); verify the entry isn't mislabeled. The 0317 CB (2023) is missing.
3. **Cleveland `cbx-irons`** — confirm this is the 2017 **Launcher CBX** iron set and not conflated with the CBX wedge line.
4. **Ben Hogan `edge-irons`** — ambiguous between the vintage (1989) Edge and the modern company's Edge; the vintage **Edge GS** is listed separately below.
5. **Titleist unversioned `t100s-irons` / `t300-irons`** — both had 2021 refresh generations; consider versioning these entries (T300 2021 is a candidate below).
6. **Non-existent / alias models confirmed during research** (do NOT add): Ping Zing 5 (never existed); Mizuno Pro 118/318/518 (JDM aliases of MP-18 SC/MMC/HMB already on site); Miura TC-101 (JDM alias of TC-201); Srixon Z 555 (not an iron); Mizuno MP-11/27/31/35 (no evidence); Ping G2 EZ, G5L (no evidence).

---

## 3. Prioritized batches

### Batch 1 — Highest search demand (50)

All verified **high**-priority models plus the strongest mediums. Several fill holes in generation runs the site already covers, which makes them cheap wins for internal linking.

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | TaylorMade | P770 (2020) | 2020 | Missing generation in an existing run; hugely searched hollow-body gen | high |
| 2 | Titleist | T200 (2021) | 2021 | Missing generation (site has 2019/2023); heavily bought used | high |
| 3 | Callaway | Rogue X | 2018 | One of the most-bought used Callaway GI irons | high |
| 4 | Callaway | Apex Pro 19 | 2019 | Companion to existing Apex 19 entry | high |
| 5 | Callaway | Apex Pro 16 | 2016 | Companion to existing Apex CF16 entry | high |
| 6 | Callaway | Apex Pro (2014) | 2014 | The original Apex Pro — major gap in Apex coverage | high |
| 7 | Callaway | Rogue ST Max OS | 2022 | Widely bought used; completes 4-model Rogue ST line | high |
| 8 | Callaway | X Forged CB (2021) | 2021 | Recent tour cavity back (site has only X Forged 2018) | high |
| 9 | Mizuno | JPX 923 Hot Metal Pro | 2022 | Missing member of the 923 Hot Metal family | high |
| 10 | Mizuno | JPX 921 Hot Metal Pro | 2020 | Compact Hot Metal, confirmed heavy used volume | high |
| 11 | Mizuno | JPX 919 Hot Metal Pro | 2018 | Big used seller missing from the 919 family | high |
| 12 | Mizuno | JPX 900 Tour | 2016 | Missing Tour model of the JPX 900 family | high |
| 13 | Mizuno | JPX 850 | 2014 | Non-forged sibling of existing JPX 850 Forged | high |
| 14 | Mizuno | JPX 825 Pro | 2012 | Hugely popular forged players-GI iron | high |
| 15 | Ping | i (2015) | 2015 | The "Ping i" between i25 and i200; big used seller | high |
| 16 | Ping | i3+ | 2002 | Hugely popular update; very common used (Blade + O-Size heads) | high |
| 17 | PXG | 0311 XP Gen4 | 2021 | Very popular forgiving model; site jumps Gen5→Gen8 for XP | high |
| 18 | PXG | 0311 XP Gen6 | 2023 | Top used-PXG search; pairs with existing P Gen6 | high |
| 19 | PXG | 0311 XP Gen7 | 2025 | Current line; pairs with existing P Gen7 | high |
| 20 | PXG | 0211 DC | 2021 | DualCOR budget line, very heavy used volume | high |
| 21 | PXG | 0211 XCOR2 | 2022 | Current-era 0211 refresh, sold in volume direct | high |
| 22 | Cobra | King Max | 2026 | Current max-forgiveness GI line at retail | high |
| 23 | Cobra | Air-X | 2021 | Budget lightweight GI set, heavy used volume | high |
| 24 | Cobra | Air-X (2024) | 2024 | Second-gen Air-X, current budget seller | high |
| 25 | Cobra | F-Max | 2017 | Original F-Max senior/moderate-speed line (site has only Airspeed) | high |
| 26 | Cleveland | Launcher UHX | 2019 | Utility-hollow progressive set, big used seller | high |
| 27 | Cleveland | HALO XL Full-Face | 2024 | Current hybrid-iron max-GI line | high |
| 28 | Wilson | Launch Pad | 2020 | Original Launch Pad (site has only Launch Pad 2) | high |
| 29 | Wilson | Staff D9 Forged | 2022 | Recent forged players-distance, actively searched | high |
| 30 | Nike | Vapor Fly Pro | 2016 | Rory-era iron; among the most-searched Nike sets | high |
| 31 | Adams | Idea (2024) | 2024 | TaylorMade's Adams revival, current retail | high |
| 32 | Miura | MB-001 | 2015 | The "Baby Blade" — Miura's most iconic modern blade | high |
| 33 | Miura | CB-57 | 2019 | Very popular mid-size forged CB | high |
| 34 | Sub 70 | 639 CB | 2020 | Core current lineup forged CB | high |
| 35 | Sub 70 | 639 MB | 2020 | Core current lineup compact blade | high |
| 36 | Sub 70 | 799 | 2021 | Max-forgiveness hollow body, current lineup | high |
| 37 | New Level | 902-PD | 2022 | Their most-reviewed model | high |
| 38 | Edel | SMS | 2022 | Adjustable-weighting players distance; big fitting-channel demand | high |
| 39 | Edel | SMS Pro | 2022 | MyGolfSpy top-finisher players cavity | high |
| 40 | Fourteen | TC-7 Forged | 2021 | MyGolfSpy 2022 Most Wanted Player's Iron winner | high |
| 41 | TaylorMade | Tour Preferred MC (2014) | 2014 | Popular tour iron preceding P700 series | medium |
| 42 | TaylorMade | SIM2 Max OS | 2021 | Recent oversize variant, commonly searched | medium |
| 43 | TaylorMade | M CGB | 2017 | Heavily marketed max-distance iron | medium |
| 44 | Callaway | X-24 Hot | 2010 | Last X-number GI line, big seller | medium |
| 45 | Callaway | Diablo Edge | 2010 | High-volume GI seller, still traded used | medium |
| 46 | Titleist | 718 T-MB | 2017 | Hollow-body set sold 2–PW; completes 718 family | medium |
| 47 | Titleist | 755 | 2006 | Mainstream player's iron replaced by AP1 | medium |
| 48 | Ping | Eye 2 Plus | 1989 | Enormous installed base still in play | medium |
| 49 | Srixon | Z 965 | 2016 | Missing muscle back of the 565/765/965 line | medium |
| 50 | PXG | 0311 P Gen3 | 2020 | Gen3 players iron, big used volume | medium |

### Batch 2 — Strong mediums: recent generations & line completions (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | TaylorMade | SIM Max OS | 2020 | Oversize SIM Max, common used buy | medium |
| 2 | TaylorMade | Tour Preferred CB (2014) | 2014 | Still commonly played tour CB | medium |
| 3 | TaylorMade | Tour Preferred MB (2014) | 2014 | Last TP blade before P7 series | medium |
| 4 | TaylorMade | AeroBurner | 2015 | Distance line sold alongside RSi | medium |
| 5 | TaylorMade | RocketBladez Tour | 2013 | Tour version of existing RocketBladez entry | medium |
| 6 | TaylorMade | RocketBallz Max | 2012 | Metalwood-construction GI iron | medium |
| 7 | TaylorMade | Kalea Premier | 2022 | Current-era women's line | medium |
| 8 | TaylorMade | Kalea | 2016 | Flagship women's line, genuinely searched | medium |
| 9 | TaylorMade | P750 Tour Proto | 2017 | Tour proto of first P-series wave | medium |
| 10 | TaylorMade | P730 | 2017 | P-series blade before P7MB, tour-played | medium |
| 11 | Callaway | Rogue Pro | 2018 | Pro model of 2018 Rogue | medium |
| 12 | Callaway | Mavrik Pro | 2020 | Pro member of Mavrik family | medium |
| 13 | Callaway | Rogue ST Max OS Lite | 2022 | Confirmed lightweight OS variant | medium |
| 14 | Callaway | Paradym Ai Smoke Max Fast | 2024 | Confirmed lightweight Ai Smoke member | medium |
| 15 | Callaway | Elyte Max Fast | 2025 | Confirmed lightweight Elyte model | medium |
| 16 | Callaway | Big Bertha (2023) | 2023 | Current-era BB irons | medium |
| 17 | Callaway | Great Big Bertha (2023) | 2023 | Premium lightweight GBB, current catalog | medium |
| 18 | Callaway | Big Bertha (2014) | 2014 | Cup-face BB relaunch, popular used | medium |
| 19 | Callaway | Big Bertha OS | 2016 | Oversize exo-cage generation | medium |
| 20 | Callaway | X2 Hot Pro | 2014 | Pro model of existing X2 Hot | medium |
| 21 | Callaway | X Hot Pro | 2013 | Pro model of existing X Hot | medium |
| 22 | Callaway | XR Pro | 2015 | Pro version of existing XR | medium |
| 23 | Callaway | Steelhead XR Pro | 2016 | Pro version of existing Steelhead XR | medium |
| 24 | Callaway | Apex MB (2018) | 2018 | Blade generation before Apex MB 21 | medium |
| 25 | Callaway | Edge (Costco) | 2019 | Costco-exclusive set with outsized spec-search volume | medium |
| 26 | Callaway | Solaire | 2012 | Long-running women's set, genuinely searched | medium |
| 27 | Titleist | ZB | 2008 | Forged blend blade launched with original AP line | medium |
| 28 | Titleist | ZM | 2008 | Forged muscle-back of the 2008 lineup | medium |
| 29 | Titleist | AP1 (2008) | 2008 | Original AP1 — site has AP2 2008 but not its pair | medium |
| 30 | Titleist | 710 CB | 2009 | Site has 710 MB but not 710 CB | medium |
| 31 | Titleist | 775.CB | 2006 | Larger forged CB replaced by AP2 | medium |
| 32 | Titleist | 735.CM | 2005 | Popular forged cavity blade, still bought used | medium |
| 33 | Titleist | 704.CB | 2004 | Forged CB between 690.CB and 695.CB | medium |
| 34 | Titleist | 680 | 2003 | Forged tour blade of the 690-era lineup | medium |
| 35 | Ping | Karsten (reissue) | 2014 | Distance iron reviving the Karsten name | medium |
| 36 | Ping | G Le3 | 2023 | Current women's line, active demand | medium |
| 37 | Ping | i3 Blade | 2000 | Blade sibling of existing i3 O-Size | medium |
| 38 | Ping | S59 | 2003 | First S-series tour blade (site has S55–S58) | medium |
| 39 | PXG | 0311 T Gen4 | 2021 | Missing T of Gen4 | medium |
| 40 | PXG | 0311 XP Gen3 | 2020 | Gen3 forgiveness model | medium |
| 41 | PXG | 0311 T Gen3 | 2020 | Gen3 tour model | medium |
| 42 | PXG | 0311 P Gen2 | 2018 | Gen2 players iron | medium |
| 43 | PXG | 0311 T Gen2 | 2018 | Gen2 tour model | medium |
| 44 | PXG | 0311 XF Gen2 | 2018 | Xtreme Forgiveness Gen2, common used | medium |
| 45 | PXG | 0311 (Gen1) | 2016 | The original PXG iron that launched the brand | medium |
| 46 | PXG | 0317 CB | 2023 | Tour cavity back paired with 0317 ST | medium |
| 47 | PXG | 0317 ST | 2022 | Milled blade (verify vs existing "0317 T" entry) | medium |
| 48 | Mizuno | JPX EZ | 2013 | Distance/GI line (2nd gen 2015 may warrant own entry) | medium |
| 49 | Mizuno | JPX EZ Forged | 2013 | Forged EZ (2nd gen 2015) | medium |
| 50 | Mizuno | MP-55 | 2016 | Half-cavity forged iron, widely searched | medium |

### Batch 3 — Mediums: 2000s–2010s core catalog (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | Mizuno | JPX 923 Hot Metal HL | 2022 | High-launch member of the 923 HM family | medium |
| 2 | Mizuno | JPX 925 Hot Metal HL | 2024 | High-launch member of the current 925 family | medium |
| 3 | Mizuno | JPX 800 Pro | 2010 | Forged Pro launched with existing JPX 800 | medium |
| 4 | Mizuno | MX-200 | 2008 | Award-winning Y-Tune forged GI iron | medium |
| 5 | Mizuno | MX-19 | 2008 | Pocket-cavity forged GI, still listed used | medium |
| 6 | Mizuno | MX-20 | 2001 | First forged MX game-improvement iron | medium |
| 7 | TaylorMade | Tour Preferred CB (2011) | 2011 | 2011 TP line (resolve vs existing TP CB entry) | medium |
| 8 | TaylorMade | Tour Preferred MB (2011) | 2011 | 2011 TP blade (resolve vs existing TP MB entry) | medium |
| 9 | TaylorMade | Tour Preferred MC (2011) | 2011 | Mid-cavity of 2011 TP line | medium |
| 10 | TaylorMade | Tour Preferred (2009) | 2009 | Single-model forged TP, 2nd Swing confirmed | medium |
| 11 | TaylorMade | Tour Burner | 2008 | Distance-players crossover, active used listing | medium |
| 12 | TaylorMade | Burner XD | 2008 | Titanium-face oversized distance iron | medium |
| 13 | TaylorMade | R7 XD | 2009 | CNC-milled Ti-face GI iron | medium |
| 14 | TaylorMade | RAC CB TP | 2005 | rac TP cavity-back played on tour | medium |
| 15 | TaylorMade | RAC MB | 2003 | Forged muscleback with cult following | medium |
| 16 | TaylorMade | RAC HT | 2004 | High-trajectory GI rac model | medium |
| 17 | TaylorMade | 200 Steel | 1999 | Popular late-90s players-GI iron | medium |
| 18 | TaylorMade | Burner Oversize | 1996 | Best-selling 90s GI iron, still listed used | medium |
| 19 | Callaway | X Forged (2013) | 2013 | Third-gen X Forged | medium |
| 20 | Callaway | X Forged (2009) | 2009 | Second-gen X Forged | medium |
| 21 | Callaway | X Forged (2007) | 2007 | First X Forged, tour-played classic | medium |
| 22 | Callaway | X-22 Tour | 2009 | Tour version of existing X-22 | medium |
| 23 | Callaway | X-20 Tour | 2007 | Tour version of the massive-selling X-20 | medium |
| 24 | Callaway | X-Tour | 2005 | Two-piece forged tour iron | medium |
| 25 | Callaway | RAZR X Tour | 2011 | Tour model of RAZR X line | medium |
| 26 | Callaway | RAZR X Forged | 2011 | Forged RAZR X | medium |
| 27 | Callaway | RAZR X HL | 2011 | Very common used high-launch set | medium |
| 28 | Callaway | Diablo Forged | 2009 | Forged distance iron | medium |
| 29 | Callaway | Big Bertha (1994) | 1994 | First Big Bertha irons, huge seller | medium |
| 30 | Titleist | DCI 990B | 2000 | Tour-blade companion to existing DCI 990 | medium |
| 31 | Titleist | DCI 962B | 1997 | Blade companion to existing DCI 962 | medium |
| 32 | Titleist | T300 (2021) | 2021 | Second-gen T300 from the 2021 refresh | medium |
| 33 | Ping | Rapture | 2006 | Premium multi-material GI line | medium |
| 34 | Ping | Rapture V2 | 2008 | Titanium-face follow-up | medium |
| 35 | Cobra | King Forged Tec (2016) | 2016 | Original PWRSHELL Forged Tec (site has 2019/2022) | medium |
| 36 | Cobra | King Forged Tec X | 2022 | Wider-body X variant, still in play | medium |
| 37 | Cobra | F-Max Superlite | 2019 | Generation between F-Max and Airspeed | medium |
| 38 | Cobra | T-Rail | 2019 | Rail-sole hybrid-iron set (2021 refresh) | medium |
| 39 | Cobra | King OS | 2016 | 2016 King Oversize GI iron | medium |
| 40 | Cobra | Fly-Z+ | 2015 | Players Fly-Z, Rickie Fowler era | medium |
| 41 | Cobra | Fly-Z XL | 2015 | Super-GI hybrid-combo Fly-Z | medium |
| 42 | Cobra | Bio Cell+ | 2014 | Forged distance version of Bio Cell | medium |
| 43 | Cobra | S9 | 2008 | Hugely sold late-2000s GI iron | medium |
| 44 | Cobra | FP | 2006 | Full-perimeter GI line, very common used | medium |
| 45 | Cobra | Baffler XL | 2012 | Hybrid-iron combo set | medium |
| 46 | Cobra | King Cobra Oversize | 1994 | The 90s oversize iron that built the brand | medium |
| 47 | Cleveland | 588 Altitude | 2013 | Ultra-high-launch 588, strong-loft oddity | medium |
| 48 | Cleveland | 588 MB | 2013 | Forged muscle back from the 588 relaunch | medium |
| 49 | Cleveland | 588 CB | 2013 | Forged cavity back sibling | medium |
| 50 | Cleveland | Launcher CBX | 2017 | Cavity-back Launcher preceding UHX | medium |

### Batch 4 — Mediums: mid-tier brands & modern JDM (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | Cleveland | TA7 | 1999 | Best-known Tour Action forged iron | medium |
| 2 | Srixon | I-701 Tour | 2007 | Forged tour iron with GolfWRX cult following | medium |
| 3 | Wilson | Staff D7 Forged | 2020 | Forged players-distance D7 variant | medium |
| 4 | Wilson | Staff D350 | 2017 | Last of the pre-D7 distance line | medium |
| 5 | Wilson | Staff D200 | 2015 | Superlight distance iron | medium |
| 6 | Wilson | Staff D100 | 2013 | Distance line reboot | medium |
| 7 | Wilson | Staff C200 | 2016 | FLX Face C-series before C300 | medium |
| 8 | Wilson | Staff FG Tour M3 | 2015 | Muscle-cavity tour iron | medium |
| 9 | Nike | VR-S Covert 2.0 | 2014 | Second-gen Covert (site covers 2013 only) | medium |
| 10 | Nike | VR-S | 2012 | NexCOR-face GI iron | medium |
| 11 | Nike | VR-S Forged | 2012 | Forged players VR-S | medium |
| 12 | Nike | VR Pro Cavity | 2011 | Pocket-cavity companion to existing VR Pro entries | medium |
| 13 | Nike | Slingshot 4D | 2009 | Final Slingshot generation | medium |
| 14 | Nike | Slingshot OSS | 2006 | Oversize Slingshot, huge seller | medium |
| 15 | Nike | Pro Combo | 2003 | Iconic split cavity/blade combo set | medium |
| 16 | Adams | Idea (original) | 2003 | The first Idea set that defined the hybrid-iron category | medium |
| 17 | Adams | Idea a2 | 2005 | Second-gen Idea | medium |
| 18 | Adams | Idea a2 OS | 2005 | Mass-seller oversize a2 | medium |
| 19 | Adams | Idea a3 | 2007 | Third-gen with hybrid long irons | medium |
| 20 | Adams | Idea a7 OS | 2009 | Oversize a7 (site has a7 only) | medium |
| 21 | Adams | Idea a12 OS | 2011 | Oversize a12 (site has a12 only) | medium |
| 22 | Adams | Idea Tech a4 | 2008 | Boxer-frame tech set (distinct from site's 2012 Tech V4) | medium |
| 23 | Adams | Idea Tech V3 | 2010 | Forged Tech gen between a4 and V4 | medium |
| 24 | Adams | Idea Pro Forged | 2006 | Tour-played forged Idea Pro | medium |
| 25 | Adams | Idea Pro Gold | 2008 | Forged players line with tour presence | medium |
| 26 | Adams | Idea Black CB2 | 2011 | Widely played on Champions Tour | medium |
| 27 | Adams | Idea MB2 | 2011 | Cult-classic forged muscle back | medium |
| 28 | Bridgestone | 220 MB | 2022 | Muscle back of the 22-series (site has 221CB) | medium |
| 29 | Bridgestone | 222 CB+ | 2022 | Pocket-cavity distance model of the 22-series | medium |
| 30 | Bridgestone | Tour B X-CBP | 2019 | Pocket-cavity sibling of existing X-CB | medium |
| 31 | Bridgestone | Tour B X-Blade | 2017 | Modern Bridgestone muscle back | medium |
| 32 | Bridgestone | Tour B JGR HF2 | 2018 | Hybrid-forged distance iron | medium |
| 33 | Bridgestone | J15CB | 2015 | Cavity back of the US-market J15 relaunch | medium |
| 34 | Ben Hogan | Apex Edge | 2002 | Heavily searched forged GI Apex line | medium |
| 35 | Ben Hogan | Apex Edge Pro | 2003 | Players version, tour-used | medium |
| 36 | Ben Hogan | Apex Plus | 1999 | Forged Apex generation before Edge | medium |
| 37 | Ben Hogan | Apex (1972) | 1972 | The original Hogan Apex blade dynasty | medium |
| 38 | Tommy Armour | 855s Silver Scot | 1994 | Follow-up to the 845s, still commonly owned | medium |
| 39 | Tommy Armour | 845 (2019) | 2019 | Modern Dick's reissue of the 845 name | medium |
| 40 | Tommy Armour | 845 Max | 2020 | Max-forgiveness modern 845 | medium |
| 41 | Tommy Armour | 845+ | 2024 | Newest 845 generation | medium |
| 42 | Tommy Armour | Atomic | 2018 | Hollow-body max-distance, heavily promoted at Dick's | medium |
| 43 | Honma | TW737 V | 2016 | Best-known TW737 variant, forged players CB | medium |
| 44 | Honma | TW737 P | 2016 | Pocket-cavity players distance | medium |
| 45 | Honma | TW737 Vs | 2016 | Larger strong-loft forged CB | medium |
| 46 | Honma | T//World-X (TW-X) | 2019 | Hollow-body players distance, Justin Rose era | medium |
| 47 | Honma | T//World GS | 2021 | Game-improvement line, official NA launch | medium |
| 48 | Honma | Beres 08 | 2021 | Luxury line gen 08 (incl. Black/Aizu editions) | medium |
| 49 | Honma | Beres 09 | 2023 | Current luxury generation | medium |
| 50 | Miura | CB-1008 | 2017 | Classic larger CB, MG Collection US release | medium |

### Batch 5 — Mediums: new brands, DTC & remaining JDM (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | Miura | MB-5005 | 2017 | Classic thin-topline blade, purist favorite | medium |
| 2 | Miura | IC-601 | 2017 | Hollow-body distance set, unusual for Miura | medium |
| 3 | Miura | PP-9003 | 2018 | Passing Point players distance | medium |
| 4 | XXIO | XXIO Eleven | 2020 | 11th gen, first dual-lineup year with X | medium |
| 5 | XXIO | XXIO 10 | 2018 | 10th-gen flagship lightweight GI | medium |
| 6 | XXIO | XXIO 9 | 2016 | 9th-gen flagship | medium |
| 7 | XXIO | X (2020) | 2020 | First-gen athletic X line (site has only 2022) | medium |
| 8 | Tour Edge | Hot Launch C523 | 2023 | C-spec gen before existing C524 | medium |
| 9 | Tour Edge | Hot Launch E523 | 2023 | E-spec gen before existing E524 | medium |
| 10 | Tour Edge | Hot Launch C522 | 2022 | C-spec with Vibrcor/Diamond Face 2.0 | medium |
| 11 | Tour Edge | Hot Launch E522 | 2022 | E-spec super-GI iron-wood | medium |
| 12 | Tour Edge | Hot Launch C521 | 2021 | Competition Spec GI value line | medium |
| 13 | Tour Edge | Hot Launch E521 | 2021 | Extreme Spec super-GI iron-wood | medium |
| 14 | Tour Edge | Exotics C721 | 2021 | Forged-face players distance | medium |
| 15 | Tour Edge | Exotics E721 | 2021 | Hollow-body GI Exotics | medium |
| 16 | Tour Edge | Hot Launch HL4 | 2019 | Popular budget GI | medium |
| 17 | Tour Edge | Hot Launch X525 | 2025 | Current 525-series (verify C/E vs X naming) | medium |
| 18 | Sub 70 | 699 (original) | 2018 | Original hollow-body GI (site has only V2) | medium |
| 19 | Sub 70 | 699 Pro (original) | 2019 | Original compact hollow (site has only Pro V2) | medium |
| 20 | Sub 70 | 649 MB Tour | 2021 | Tour blade with 0.5mm offset across set | medium |
| 21 | New Level | 902 Forged | 2018 | Original launch model | medium |
| 22 | New Level | 1031 Forged | 2018 | Strong-loft mid-size forged | medium |
| 23 | Yonex | Ezone GS | 2021 | Mainstream GI with strong UK retail presence | medium |
| 24 | Yonex | Ezone GT | 2026 | Current super-GI generation | medium |
| 25 | Fourteen | TB-5 Forged | 2021 | Players blade, TXG-reviewed | medium |
| 26 | Fourteen | TC-788 Forged | 2018 | Forged distance iron with US press coverage | medium |
| 27 | Maltby | TS-1 | 2018 | Billet-forged CB, huge GolfWorks DIY following | medium |
| 28 | Maltby | TS-2 | 2019 | Players distance, MyGolfSpy value darling | medium |
| 29 | Maltby | TS-3 | 2020 | Forged super-GI | medium |
| 30 | Maltby | TS-4 | 2021 | Billet-forged blade (MMB-17 successor) | medium |
| 31 | Wishon | Sterling Single Length | 2016 | Best-known single-length set of the Bryson era | medium |
| 32 | Epon | AF-306 | 2022 | Premium Endo-forged players CB, current | medium |
| 33 | Epon | AF-506 | 2022 | Players distance, current | medium |
| 34 | Epon | AF-706 | 2020 | Hollow-body distance | medium |
| 35 | Vega | Mizar | 2019 | Forged players CB, UK/EU review coverage | medium |
| 36 | Vega | Mizar Tour | 2022 | Compact players distance, GolfWRX-reviewed | medium |
| 37 | Haywood | Signature | 2022 | Hollow-body players distance, Canadian DTC | medium |
| 38 | Haywood | CB | 2021 | Milled 1020 forged CB, "P7CB rival" press | medium |
| 39 | Haywood | MB | 2021 | Milled forged blade | medium |
| 40 | Stix | Perform | 2021 | High-volume beginner DTC set | medium |
| 41 | Proto-Concept | C01 | 2020 | Endo-forged muscleback, TXG/fitter following | medium |
| 42 | Proto-Concept | C05 | 2020 | Players distance, most-fitted model | medium |
| 43 | TaylorMade | SpeedBlade HL | 2014 | High-launch variant of existing SpeedBlade | low |
| 44 | TaylorMade | RSi TP | 2015 | Forged TP model of the RSi family | low |
| 45 | TaylorMade | Burner SuperFast 2.0 | 2011 | Superlight distance line | low |
| 46 | Callaway | Big Bertha (2008) | 2008 | Last of the classic BB iron runs | low |
| 47 | Ping | G Le2 | 2019 | Second-gen women's line, still bought used | low |
| 48 | Mizuno | MX-1000 | 2009 | Hot-face max-distance MX flagship | low |
| 49 | Mizuno | MX-100 | 2008 | Ultra-pocket-cavity max-forgiveness iron | low |
| 50 | Mizuno | MX-900 | 2006 | Cast GI model of the mid-2000s MX line | low |

### Batch 6 — Lows: mainstream back catalog, 1990s–2010s (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | TaylorMade | 320 | 2001 | 300-series sibling of existing 300 Forged | low |
| 2 | TaylorMade | 360 | 2002 | Game-improvement member of 300 series | low |
| 3 | TaylorMade | RAC MB TP | 2005 | Second-gen rac TP blade | low |
| 4 | TaylorMade | R7 TP | 2007 | TP version of the r7 iron | low |
| 5 | TaylorMade | Burner LCG | 1997 | Low-CG follow-up to Burner Oversize | low |
| 6 | TaylorMade | SuperSteel | 1999 | Thin-face distance iron, still traded used | low |
| 7 | TaylorMade | Firesole | 1999 | Multi-material Ti/steel irons with tungsten sole | low |
| 8 | TaylorMade | Burner Bubble | 1995 | Bubble-shaft era 90s irons | low |
| 9 | TaylorMade | ICW 11 | 1988 | Pre-1994 classic cavity back, collector searches | low |
| 10 | Callaway | RAZR X Muscleback | 2012 | RAZR-era blade | low |
| 11 | Callaway | RAZR X Black | 2012 | Budget/retail RAZR variant | low |
| 12 | Callaway | Epic Forged Star | 2019 | Ultralight premium Epic Forged variant | low |
| 13 | Callaway | Paradym Star | 2023 | Ultralight premium Paradym variant | low |
| 14 | Callaway | X Series N415 | 2015 | Budget retail X Series iron | low |
| 15 | Callaway | X-16 Pro Series | 2002 | Pro version of existing X-16 | low |
| 16 | Callaway | X-18 Pro Series | 2004 | Pro version of existing X-18 | low |
| 17 | Callaway | Big Bertha (2002) | 2002 | Stainless BB of the early 2000s | low |
| 18 | Callaway | Big Bertha (2004) | 2004 | Mid-2000s BB generation | low |
| 19 | Callaway | Big Bertha (2006) | 2006 | Mid-2000s BB generation | low |
| 20 | Callaway | Big Bertha Fusion | 2004 | Multi-material Fusion irons | low |
| 21 | Callaway | Fusion Wide Sole | 2007 | Super-GI wide-sole Fusion | low |
| 22 | Callaway | FT i-brid | 2008 | Distinctive hybrid-like iron set | low |
| 23 | Callaway | Hawk Eye | 2000 | GBB Hawk Eye tungsten-weighted irons | low |
| 24 | Callaway | Hawk Eye VFT | 2002 | VFT titanium follow-up | low |
| 25 | Callaway | Great Big Bertha Tungsten Titanium | 1997 | Ti body + tungsten insert premium iron | low |
| 26 | Callaway | Big Bertha Gold | 1996 | Aluminum-bronze BB follow-up | low |
| 27 | Callaway | S2H2 | 1991 | Original Callaway irons, collector interest | low |
| 28 | Titleist | DCI 762B | 2002 | Blade version of existing DCI 762 | low |
| 29 | Titleist | DCI 981SL | 1998 | Super-lightweight 981 variant | low |
| 30 | Titleist | DCI Black | 1993 | Original DCI player's model | low |
| 31 | Titleist | DCI Oversize + | 1996 | Standard Oversize + (site has Gold variant) | low |
| 32 | Titleist | 804.OS | 2004 | Titleist's mid-2000s oversize GI model | low |
| 33 | Titleist | 731.PM | 2002 | Phil Mickelson limited-edition blade, cult item | low |
| 34 | Titleist | Tour Model | 1981 | Classic pre-DCI forged blades, collector lookups | low |
| 35 | Titleist | T100S (2021) | 2021 | 2021 refresh of T100S (verify vs unversioned entry) | low |
| 36 | Ping | Eye 2 XG | 2008 | Modern conforming-groove Eye 2 reissue | low |
| 37 | Ping | Karsten I/II/III/IV | 1969–76 | Original Karsten irons that founded the brand | low |
| 38 | Ping | GLe | 2016 | First-gen women's G Le line | low |
| 39 | Ping | Rhapsody | 2007 | Women's line (2nd gen 2015) | low |
| 40 | Ping | Faith | 2011 | Women's line of the early 2010s | low |
| 41 | Ping | Serene | 2013 | Women's line between Faith and G Le | low |
| 42 | Mizuno | MX-15 | 2002 | Cast GI preceding MX-23 | low |
| 43 | Mizuno | MP-H4 | 2012 | Hollow-construction full iron set | low |
| 44 | Mizuno | MP-H5 | 2014 | Hollow full-set successor | low |
| 45 | Mizuno | MP-9 | 1988 | Early MP-series blade | low |
| 46 | Mizuno | T-Zoid | 1996 | Late-90s mainstream iron family | low |
| 47 | Mizuno | T-Zoid Pro | 1997 | Forged player's T-Zoid | low |
| 48 | Mizuno | TN-87 | 1987 | Legendary Grain Flow blade, cult JDM classic | low |
| 49 | Mizuno | TN-93 | 1994 | Successor to TN-87/TN-91 | low |
| 50 | Mizuno | TP-9 | 1986 | Tour Professional-series forged blade | low |

### Batch 7 — Lows: mid-tier brand back catalog (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | Mizuno | TP-11 | 1988 | TP-series blade follow-up | low |
| 2 | Mizuno | MS-1 | c.1983 | Early Grain Flow forged blade | low |
| 3 | Mizuno | MS-11 | c.1988 | Late-80s MS-series blade | low |
| 4 | Cobra | S9-1 | 2009 | Players follow-up to S9 (Pro/standard) | low |
| 5 | Cobra | S2 Forged | 2010 | Forged players S2 | low |
| 6 | Cobra | King Forged MB | 2020 | Muscle-back companion to existing King Forged CB | low |
| 7 | Cobra | King Cobra II Oversize | 1996 | Second-gen 90s oversize | low |
| 8 | Cobra | King Cobra SS | 1999 | SS-generation base model | low |
| 9 | Cobra | Gravity Back | 2000 | Early-2000s tungsten GI iron | low |
| 10 | Cleveland | 588 TT | 2013 | Tour Trajectory cast 588 | low |
| 11 | Cleveland | 588 MT | 2013 | Mid Trajectory GI 588 | low |
| 12 | Cleveland | CG1 | 2004 | Early-2000s forged blade | low |
| 13 | Cleveland | CG2 | 2005 | Forged cavity companion to CG1 | low |
| 14 | Cleveland | CG Gold | 2007 | Well-reviewed forged GI iron | low |
| 15 | Cleveland | CG Red | 2007 | Distance/GI sibling of CG Gold | low |
| 16 | Cleveland | CG Black | 2015 | Ultralight distance iron (also 2011 gen) | low |
| 17 | Cleveland | TA1 Form Forged | 1998 | Tour Action players model | low |
| 18 | Cleveland | TA2 | 1996 | Early Tour Action model | low |
| 19 | Cleveland | TA3 | 2000 | Tour Action GI model | low |
| 20 | Cleveland | TA5 | 1997 | Tour Action mid-handicap forged iron | low |
| 21 | Cleveland | TA6 | 2001 | Tour Action oversize model | low |
| 22 | Cleveland | VAS | 1993 | Famous Corey Pavin one-piece design | low |
| 23 | Srixon | Z-TX | 2010 | Tour cavity pre-Z-series naming | low |
| 24 | Srixon | I-701 | 2007 | Standard forged 701 model | low |
| 25 | Srixon | I-506 | 2005 | Mid-2000s forged players cavity | low |
| 26 | Srixon | I-403 AD | 2004 | Early GI Srixon iron | low |
| 27 | Srixon | I-302 | 2003 | Srixon's early forged players iron | low |
| 28 | Wilson | Staff FG Tour V2 | 2012 | Second-gen FG Tour forged cavity | low |
| 29 | Wilson | Staff FG Tour | 2010 | Original FG Tour players iron | low |
| 30 | Wilson | Staff Di7 | 2006 | Mid-2000s max-distance GI iron | low |
| 31 | Wilson | Staff Di9 | 2008 | Distance iron between Di7 and Di11 | low |
| 32 | Wilson | Staff Di11 | 2010 | Last of the Di distance series | low |
| 33 | Wilson | Deep Red | 2002 | Early-2000s distance line, nostalgia searches | low |
| 34 | Wilson | Fat Shaft | 1998 | Oversize-hosel iron, well remembered | low |
| 35 | Wilson | Staff Tour Blade | 1987 | Classic button-back era blade | low |
| 36 | Nike | VR Full Cavity | 2010 | Victory Red full-cavity GI iron | low |
| 37 | Nike | VR Split Cavity | 2010 | Victory Red split-cavity iron | low |
| 38 | Nike | Slingshot Tour | 2007 | Compact tour take on the Slingshot | low |
| 39 | Nike | SQ MachSpeed | 2010 | Sasquatch-era GI iron | low |
| 40 | Nike | Pro Combo OS | 2004 | Oversize Pro Combo | low |
| 41 | Nike | CCi Forged | 2006 | Polymer-slot forged iron | low |
| 42 | Nike | Ignite | 2005 | Mid-2000s GI iron | low |
| 43 | Nike | NDS | 2007 | Budget-friendly distance set | low |
| 44 | Nike | Forged Blades | 2002 | Nike's first blades | low |
| 45 | Adams | Idea a3 OS | 2007 | Oversize a3 variant | low |
| 46 | Adams | Idea Tech a4 OS | 2008 | Oversize Tech a4 | low |
| 47 | Adams | Idea Pro Black | 2010 | Premium black-finish muscle back | low |
| 48 | Adams | Idea Pro Black CB1 | 2010 | Forged cavity of the Pro Black line | low |
| 49 | Adams | Blue | 2015 | Last original-era Adams line | low |
| 50 | Adams | Ovation | 2003 | High-launch GI set, still seen used | low |

### Batch 8 — Lows: JDM, boutique & remaining (50)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | Bridgestone | JGR HF1 | 2016 | First hybrid-forged JGR iron | low |
| 2 | Bridgestone | J15DF | 2015 | Driving-forged players-distance J15 | low |
| 3 | Bridgestone | J15DPF | 2015 | Dual-pocket forged GI model | low |
| 4 | Bridgestone | J38 CB | 2010 | Forged cavity back, JDM-quality following | low |
| 5 | Bridgestone | J38 Dual Pocket Cavity | 2010 | Pocket-cavity J38 | low |
| 6 | Bridgestone | J36 CB | 2008 | Forged cavity of the J36 line | low |
| 7 | Bridgestone | J36 Blade | 2008 | Forged blade of the J36 line | low |
| 8 | Bridgestone | J33 CB | 2005 | Early J-series forged cavity | low |
| 9 | Bridgestone | J33 Blade | 2005 | Early J-series forged blade | low |
| 10 | Ben Hogan | Apex FTX | 2004 | Callaway-era hybrid-material Apex | low |
| 11 | Ben Hogan | Apex Edge CFT | 2004 | Cavity/hybrid CFT variant | low |
| 12 | Ben Hogan | Apex Redline | 1988 | Late-80s Apex generation | low |
| 13 | Ben Hogan | Edge GS | 1992 | Early-90s vintage Edge (distinct from modern Edge) | low |
| 14 | Ben Hogan | Radial | 1987 | 80s radial-sole forged iron | low |
| 15 | Ben Hogan | Medallion | 1985 | 80s forged players cavity | low |
| 16 | Tommy Armour | 986 Tour | 1997 | Late-90s tour forged model | low |
| 17 | Tommy Armour | 845s Oversize | 1996 | Oversize spin-off of the 845s | low |
| 18 | PXG | 0311 ST Gen4 | 2021 | Blade of the Gen4 line | low |
| 19 | PXG | 0311 SGI Gen2 | 2018 | Super game-improvement Gen2 | low |
| 20 | PXG | 0311 T (Gen1) | 2016 | Original tour model | low |
| 21 | PXG | 0311 XF (Gen1) | 2016 | Original forgiveness model | low |
| 22 | PXG | 0211 ST | 2021 | Triple-forged budget blade | low |
| 23 | Honma | TW737 Vn | 2016 | Near-blade for better players | low |
| 24 | Honma | TW727 V | 2015 | Predecessor players CB, still traded | low |
| 25 | Honma | TW727 P | 2015 | Predecessor players distance | low |
| 26 | Honma | TW727 Vn | 2015 | Predecessor blade-style | low |
| 27 | Honma | Beres 07 | 2019 | Luxury multi-star GI line gen 07 | low |
| 28 | Honma | Beres Aizu | 2022 | Ultra-premium Aizu collection | low |
| 29 | Miura | CB-2008 | 2017 | MG Collection forgiving CB | low |
| 30 | XXIO | Prime 9 | 2016 | Premium ultralight line gen 9 | low |
| 31 | XXIO | Prime 10 | 2018 | Premium line gen 10 | low |
| 32 | XXIO | Prime 11 | 2020 | Premium line gen 11 | low |
| 33 | Tour Edge | Exotics EXS | 2019 | First EXS-era iron | low |
| 34 | Tour Edge | Exotics EXS 220 | 2020 | EXS follow-up | low |
| 35 | Tour Edge | Exotics EXS Pro | 2020 | Compact players EXS | low |
| 36 | Tour Edge | Hot Launch HL3 | 2018 | Prior budget generation | low |
| 37 | New Level | 623-MB | 2021 | Compact muscle back sibling (verify name) | low |
| 38 | Yonex | Ezone GS i-Tech | 2023 | Premium custom-fit GI | low |
| 39 | Yonex | Ezone Elite | 2023 | Beginner/high-handicap line | low |
| 40 | Fourteen | TB-7 Forged | 2021 | Players cavity sibling of TB-5 | low |
| 41 | Fourteen | TC-340 Forged | 2016 | One-piece forged, lowest-CG claim | low |
| 42 | Maltby | TS-1 IM | 2023 | Updated TS-1 forging | low |
| 43 | Maltby | MMB-17 | 2017 | Forged muscleback, cult component classic | low |
| 44 | Maltby | KE4 Max | 2023 | Max-forgiveness KE4 flagship | low |
| 45 | Maltby | STi2 | 2021 | GI distance component | low |
| 46 | Vega | Mizar Pro | 2023 | Muscleback for elite players | low |
| 47 | Vega | Mizar Max | 2023 | Forgiving Mizar variant | low |
| 48 | Vega | VDC | 2021 | Players distance cavity | low |
| 49 | Stix | Compete | 2024 | Newer better-player iron | low |
| 50 | Wishon | 565MC | 2016 | Forged CB, still sold via clubmakers | low |

### Batch 9 — Final tail (10)

| # | Brand | Model | Year | Why notable | Priority |
|---|---|---|---|---|---|
| 1 | Wishon | 771CSI | 2014 | GI component staple | low |
| 2 | Epon | AF-302 | 2019 | Prior-gen players CB | low |
| 3 | Epon | AF-505 | 2019 | Prior-gen players distance | low |
| 4 | Epon | AF-705 | 2018 | Prior-gen hollow body | low |
| 5 | Epon | AF-Tour CB | 2018 | Tour cavity, boutique-fitter favorite | low |
| 6 | Epon | Personal | 2016 | Luxury made-to-order blade | low |
| 7 | Proto-Concept | C03 TC | 2022 | Milled pocket-cavity players iron | low |
| 8 | Proto-Concept | C07 | 2020 | Multi-thickness-face GI | low |
| 9 | Top Flite | Gamer | 2020 | Dick's budget set; beginners search specs | low |
| 10 | Top Flite | XL | 2019 | Ubiquitous box-set iron | low |

---

## 4. New brands: add vs. skip

**Add (11):** Edel, Fourteen, Maltby, Haywood, Yonex, Epon, Vega, Proto-Concept, Stix, Wishon, Top Flite. Each has verified review coverage (MyGolfSpy/GolfWRX/TXG/Golf Monthly) and real spec-search demand; models are distributed through Batches 1, 5, 8 and 9 by priority.

**Skip (with reasons):**

| Brand | Reason |
|---|---|
| Zodia | Bespoke JDM grinder; no published standard lofts, negligible Western search |
| Onoff | Daiwa JDM line; minimal Western retail or spec searches |
| Fujimoto | Boutique JDM, marginal |
| Ram | Vintage/Amazon budget; spec searches negligible |
| Strata | Callaway boxed sets; lofts not published per-model consistently |
| MacGregor | Vintage collector interest but no reliable published loft specs; modern line is bargain-bin |
| Lynx | UK-regional revival plus vintage; below threshold |
| Orlimar / Snake Eyes / Founders Club / Slazenger / Dunlop | Budget/defunct, negligible demand |
| PRGR | Western recognition is launch monitors, not irons |
| Yamaha (RMX) | JDM-only distribution, marginal Western search |
| Grindworks / National Custom Works / Ryoma / Mystery / Crazy | Too niche |
| LA Golf | Shafts/putters; no volume iron line |
| Avoda | One prototype news spike; no stable published spec line |

---

## 5. Verification notes for content production

- Years marked "c." (Mizuno MS-series) are approximate — pre-internet JDM era. Cleveland TA-series and Ben Hogan vintage years are ±1–2 years; verify before publishing.
- Verify at add time: XXIO Prime generation years, Tour Edge X525 vs C525/E525 naming, New Level 623-MB name, Epon prior-gen years.
- Ping i3+ shipped in Blade and O-Size heads — consider one entry with two head variants (same for ISI K/Nickel as variants of the existing ISI entry).
- Borderline sets excluded but worth revisiting for max coverage: PXG 0211 Z (hybrid-style set), Honma TW747 Rose Proto (limited run, no published specs).
- Key sources used: 2nd Swing product pages, Callaway Pre-Owned, TaylorMade legacy spec PDFs, Titleist archive pages, Bridgestone archive, Pitchmarks by-year lists (Titleist/Ping/Mizuno/Cleveland/Srixon/Ben Hogan), MyGolfSpy, GolfWRX, Today's Golfer, The Hackers Paradise, Golf Monthly, GolfWorks, manufacturer sites (Tommy Armour, PXG, Wishon, Fourteen).

## 6. Summary math

| Tier | Models | Running total (from 394) |
|---|---|---|
| Batch 1 (high) | 50 | 444 |
| Batch 2 | 50 | 494 |
| Batch 3 | 50 | 544 |
| Batch 4 | 50 | 594 |
| Batch 5 | 50 | 644 |
| Batch 6 | 50 | 694 |
| Batch 7 | 50 | 744 |
| Batch 8 | 50 | 794 |
| Batch 9 | 10 | 804 |

Completing Batches 1–5 (all high + medium priority) reaches **644 models**; Batches 6–9 take the site to **~804**, comfortably inside the 750–1000 goal. If further volume is needed later, the levers are: versioning currently-unversioned entries (T100S/T300/JPX EZ gens), the borderline exclusions above, and second-tier JDM brands (Onoff, Yamaha RMX) currently on the skip list.
