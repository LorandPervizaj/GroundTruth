# Confirmed market hierarchy

Authority: owner Phase5 product definitions, not legal administrative containment.

- `arberia`: Arbëria, Arberia, Dragodan, Dragodani
- `emshir`: Kalabria, Kalabri, Emshir, Emshiri, Emshire, Në Kalabri, Në Emshir
- `pejton-lakrishte`: Pejton, Lakrishta, Lakrishte, Lakërishta
- `vranjevc-kodra-trimave`: Vranjevc, Vranjevci, Kodra e Trimave
- `llullat-dodona`: Dodona, 4 Llullat, 4 Lullat, Llullat
- `sofalia`: Sofalia, Sofali, Gërmia, Germia, Gërmi, Germi
- `bregu-i-diellit`: Bregu i Diellit, Sunny Hill

## Confirmed parent associations

- `prishtina-e-re` → `veternik`
- `parku-i-qytetit-aktash` → `aktash-muhaxhere`
- `sllovenia-sport` → `aktash-muhaxhere`, `qendra`
- `mati-1` → `matiqan`
- `mati-2` → `matiqan`
- `mati-3` → `matiqan`
- `rruga-a` → `matiqan`
- `rruga-b` → `matiqan`
- `rruga-c` → `matiqan`
- `muharrem-fejza` → `matiqan`
- `ndue-perlleshi` → `matiqan`

Sllovenia Sport is one `market_subarea:sllovenia-sport` with two typed parents.
Legacy neighborhood ID47 remains readable. `market_children` returns the same
canonical entity ID under either parent. No scalar database parent is rewritten.
Physical Rruga A/B/C use separate `physical_street:*` IDs; their old JSON road
parent assertions remain intact and are not claimed independently verified.
Legacy neighborhood records for Mati1/2/3, Prishtina e Re and Parku i Qytetit are
interpreted through typed entity redirects without deleting or renumbering them.
Qafa remains separate; no Tophane or Qendra containment is invented. Marigona Hill
and Residence remain distinct. Residential Gërmia/Sofalia is separate from the park.
Official42 local-community/OCR/OSM references stay in previous phases, unchanged.
No official community is equated to a product subarea and no polygon is fabricated.
