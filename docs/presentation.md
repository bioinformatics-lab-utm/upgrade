---
marp: true
theme: default
paginate: true
style: |
  :root {
    --color-bg: #0d1b2a;
    --color-accent: #00c9a7;
  }

  section {
    background: #0d1b2a;
    color: #e8f4f8;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 21px;
    padding: 44px 60px;
  }

  h1 {
    color: #00c9a7;
    font-size: 1.85em;
    border-bottom: 3px solid #00c9a7;
    padding-bottom: 10px;
    margin-bottom: 22px;
  }

  h2 { color: #00c9a7; font-size: 1.35em; margin-bottom: 12px; }
  h3 { color: #7ecfff; font-size: 1.05em; margin-bottom: 8px; }

  strong { color: #00c9a7; }
  em { color: #ffcc44; font-style: normal; font-weight: bold; }

  ul { padding-left: 1.3em; line-height: 1.9; }
  li { margin-bottom: 5px; }

  code {
    background: #1e3a5f;
    color: #7ecfff;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.82em;
  }

  table { width: 100%; border-collapse: collapse; font-size: 0.84em; }
  th {
    background: #1e3a5f;
    color: #00c9a7;
    padding: 9px 13px;
    text-align: left;
    border: 1px solid #2a4a6f;
  }
  td {
    padding: 7px 13px;
    border: 1px solid #1e3a5f;
    background: #162032;
  }
  tr:nth-child(even) td { background: #1a2a3f; }

  .columns { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
  .columns3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }

  .card {
    background: #162032;
    border-left: 4px solid #00c9a7;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
  }

  .card-red {
    background: #1a0d0d;
    border-left: 4px solid #e94560;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
  }

  .stat {
    background: #162032;
    border: 2px solid #00c9a7;
    border-radius: 10px;
    padding: 14px 10px;
    text-align: center;
  }
  .stat-num { font-size: 2.1em; color: #00c9a7; font-weight: bold; display: block; }
  .stat-label { font-size: 0.78em; color: #8899aa; display: block; margin-top: 4px; }

  .big-quote {
    background: #162032;
    border-left: 5px solid #00c9a7;
    border-radius: 8px;
    padding: 20px 26px;
    font-size: 1.05em;
    line-height: 1.7;
    margin: 18px 0;
  }

  .pill {
    display: inline-block;
    background: #1e3a5f;
    color: #7ecfff;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.78em;
    margin: 3px 2px;
  }

  footer { color: #556677; font-size: 0.7em; }
---

<!-- _paginate: false -->

<br><br>

# UPGRADE

## Unified Platform for Genomic Resistance Analysis,<br>Detection and Environmental Surveillance

<br>

**Platformă bioinformatică end-to-end pentru supravegherea automată**
**a rezistenței la antimicrobiene din apele reziduale urbane**

<br><br>

---
Universitatea Tehnică a Moldovei &nbsp;·&nbsp; 2025

---

# Ce problemă rezolvă UPGRADE?

<div class="columns">
<div>

### Rezistența la antibiotice ucide oameni — acum

<div class="card-red">
🦠 <strong>1.27 milioane</strong> de oameni mor în fiecare an din cauza bacteriilor rezistente la antibiotice — <em>mai mult decât HIV sau malaria</em>
</div>

<div class="card-red">
📈 Dacă nu facem nimic, până în <strong>2050</strong> vor fi <strong>10 milioane de decese/an</strong>
</div>

<div class="card-red">
🌍 Bacteriile rezistente nu respectă granițe — se răspândesc prin apă, sol, animale, oameni
</div>

### De ce apele reziduale?

> Canalizarea unui oraș concentrează bacteriile de la **toată populația** — e ca un test de sânge pentru întreg orașul. Dacă detectăm rezistența acolo, avem **6–12 luni avans** față de clinici.

</div>
<div>

### Problema concretă: nu există un instrument complet

<div class="card">
🔬 Analiza metagenomică ONT necesită <strong>18+ instrumente</strong> bioinformatice separate, fiecare cu propriul format
</div>

<div class="card">
💾 Un singur eșantion generează <strong>10–50 GB de date</strong> — infrastructură complexă, costuri mari
</div>

<div class="card">
🧑‍🔬 Necesită expertiză bioinformatică avansată — <strong>inaccesibil</strong> pentru laboratoarele clinice și autoritățile de sănătate publică
</div>

<div class="card">
🔁 Rezultatele <strong>nu sunt reproductibile</strong> fără containerizare — studii incomparabile între laboratoare
</div>

**UPGRADE rezolvă toate aceste probleme simultan:**
de la date brute FASTQ până la raport epidemiologic, **complet automat**.

</div>
</div>

---

# Scopul și obiectivele lucrării

<div class="big-quote">
Am creat o <strong>platformă completă</strong> care preia date brute de secvențiere de la orice laborator, le procesează automat prin 7 etape bioinformatice și produce rapoarte despre ce bacterii rezistente există în probă — <em>fără ca utilizatorul să știe bioinformatică</em>.
</div>

<div class="columns">
<div>

### Ce am construit

<div class="card">
🏗️ <strong>Arhitectură Lakehouse</strong> — sistem de stocare scalabil pe 3 niveluri (Bronze/Silver/Gold) care organizează automat datele genomice de la brut la raport final
</div>

<div class="card">
⚙️ <strong>Pipeline automat în 7 etape</strong> — de la FASTQ la gene de rezistență identificate, orchestrat prin Nextflow, containerizat cu Docker
</div>

<div class="card">
🌐 <strong>Interfață web</strong> accesibilă cercetătorilor fără expertiză bioinformatică — submit probă, urmărire în timp real, vizualizare rezultate
</div>

</div>
<div>

### De ce contează

<div class="card">
🔬 <strong>Long-read ONT</strong> — primul sistem open-source care combină citiri lungi nanopore cu arhitectură Lakehouse pentru AMR
</div>

<div class="card">
🔁 <strong>Reproductibilitate garantată</strong> — SHA256 la fiecare etapă, Docker cu versiuni fixate, Nextflow caching
</div>

<div class="card">
🌍 <strong>Impact real</strong> — testat pe <strong>53 eșantioane reale</strong> NCBI SRA din ape reziduale urbane, seawater și mediu
</div>

</div>
</div>

---

# Secvențierea ONT Long-Read — de ce contează pentru AMR

<div class="columns">
<div>

### Problema cu citirile scurte (Illumina, 150 bp)

- Fragmentează genele de rezistență și elementele mobile
- **Nu poate reconstrui plasmidele** — principalul vector de răspândire a ARG
- Operonii ribozomali (4–7 kb) sunt fragmentați → ambiguitate taxonomică
- Transpozoni și integroni (2–50 kb) sunt imposibil de asamblat complet

<br>

### ONT Long-Read rezolvă asta

| Caracteristică | Illumina | ONT R10.4.1 |
|---|---|---|
| Lungime citire | 150 bp | **N50 > 10 kb** |
| Acuratețe | Q30+ | **Q20+ (SUP)** |
| Plasmide | ✗ | **✓ complete** |
| Integroni/Tn | ✗ | **✓ integral** |
| Timp real | ✗ | **✓ streaming** |

</div>
<div>

### Long-read schimbă ce putem detecta

<div class="card">
🧬 <strong>Cromozomi bacterieni completi</strong> dintr-un singur scaffold — știm exact ce organism poartă rezistența
</div>

<div class="card">
💊 <strong>Plasmide 1–200+ kb reconstituite complet</strong> — putem evalua dacă o genă ARG se poate transfera la alte bacterii prin conjugare
</div>

<div class="card">
🔗 <strong>Contextul genetic complet al ARG</strong> — știm dacă o genă de rezistență este pe un integron de clasă 1, transpozon sau cromozom → evaluăm riscul de răspândire
</div>

<div class="card">
🔬 <strong>Metilaree directă</strong> — detectăm sisteme de restricție fără preparare chimică suplimentară
</div>

> UPGRADE procesează date **PromethION R10.4.1** din arhiva NCBI SRA — chimia cea mai recentă ONT cu acuratețe maximă.

</div>
</div>

---

# Pipeline Bioinformatic — 7 Etape

<div class="columns">
<div style="flex: 0.85;">

![Pipeline diagram w:420](pipeline.png)

</div>
<div>

### Instrumente cheie

| Etapă | Instrumente |
|-------|------------|
| QC | NanoPlot · Filtlong |
| Asamblare | Flye `--meta` · Medaka |
| Mapare | minimap2 `-ax map-ont` |
| Binning | MetaBAT2 · CONCOCT · dRep |
| Evaluare | CheckM v1.2.2 (MIMAG) |
| Taxonomie | Kraken2 · Bracken · GTDB-Tk |
| Adnotare | Prokka |
| ARG | DeepARG · ABRicate |

### Orchestrare

- **Nextflow DSL2** — 13 module independente
- **18 imagini Docker** cu hash SHA256 fixat
- **Redis + RQ Worker** — execuție asincronă
- Caching — reia din etapa întreruptă

</div>
</div>

---

# Arhitectura Platformei UPGRADE

<div class="columns">
<div>

![Architecture diagram w:460](db_arch.png)

</div>
<div>

### Lakehouse Medallion

| Strat | Ce conține |
|-------|-----------|
| 🥉 **Bronze** | FASTQ brut + checksum SHA256 |
| 🥈 **Silver** | MAG · ARG · taxonomie procesate |
| 🥇 **Gold** | Rapoarte epidemiologice finale |

<br>

### PostgreSQL 15 — metadate complete

- **12 tabele** în schema publică
- `samples` — probe, coordonate GPS (PostGIS 3.3), checksumuri
- `pipeline_jobs` — stare execuție, resurse, erori
- `genome_bins` — completitudine/contaminare MAG
- `arg_detections` — gene ARG identificate, baza de date sursă
- `amr_summary` — raport agregat per probă
- Interogări geospațiale: *"toate probele în 50 km de București"*

</div>
</div>

---

# Aplicația Realizată

<div class="columns">
<div>

### Dashboard web — React 18 + Sanic API

<div class="card">
📊 <strong>Monitorizare în timp real</strong> — polling HTTP la 5s, stadii: pending → running → completed
</div>

<div class="card">
🗺️ <strong>Hartă geospațială</strong> Leaflet — distribuția geografică a ARG cu clustering automat
</div>

<div class="card">
🦠 <strong>Profil taxonomic</strong> — stacked bar charts Recharts la nivel phylum/familie/specie
</div>

<div class="card">
💊 <strong>AMR Risk Score</strong> 0–100 — clasificare automată High/Medium/Low cu 25+ genuri patogene cunoscute
</div>

<div class="card">
🧬 <strong>MAG Quality Dashboard</strong> — completitudine, contaminare, filtrare MIMAG automată
</div>

</div>
<div>

### Rezultate pe date reale

<div class="columns3" style="margin-bottom: 18px;">
<div class="stat">
  <span class="stat-num">53</span>
  <span class="stat-label">eșantioane procesate</span>
</div>
<div class="stat">
  <span class="stat-num">382</span>
  <span class="stat-label">gene ARG / eșantion urban</span>
</div>
<div class="stat">
  <span class="stat-num">>95%</span>
  <span class="stat-label">completitudine MAG HQ</span>
</div>
</div>

### Export & integrare

- Rapoarte **JSON + HTML** pentru sisteme externe
- API REST documentat pentru integrare cu sisteme naționale AMR
- Toate rezultatele stocate în MinIO Silver cu path structurat: `{sample}/{pipeline_id}/`

</div>
</div>

---

# Concluzii

<div class="big-quote">
UPGRADE demonstrează că <strong>supravegherea metagenomică AMR la scară națională</strong> poate fi <em>automatizată, reproductibilă și accesibilă</em> — nu doar pentru laboratoare de elită, ci pentru orice instituție cu un server și date de secvențiere.
</div>

<div class="columns">
<div>

### Ce aduce nou

<div class="card">
🌍 <strong>Prima platformă open-source</strong> care combină ONT long-read + Lakehouse + detectare ARG + interfață web într-un singur sistem integrat
</div>

<div class="card">
⚡ <strong>De la FASTQ la raport epidemiologic</strong> complet automat — fără intervenție manuală, fără expertiză bioinformatică necesară
</div>

<div class="card">
🔬 <strong>Long-read ONT permite</strong> reconstrucția completă a plasmidelor și elementelor genetice mobile — esențial pentru evaluarea riscului de răspândire a rezistenței
</div>

</div>
<div>

### Impact potențial

- **Supraveghere continuă** a rezistenței la antibiotice în apele reziduale urbane — semnal de alertă precoce pentru sistemul de sănătate publică
- **Comparabilitate** între studii și laboratoare prin reproducibilitate garantată
- **Scalabil** de la un singur server de laborator la infrastructuri naționale

### Limitări și direcții

- RAM 120 GB necesar pentru asamblare la scară mare
- Validare experimentală sistematică în desfășurare
- **Roadmap:** suport Illumina (hybrid assembly), integrare cu rețele naționale de supraveghere AMR, extindere la ≥500 eșantioane

</div>
</div>

---

<!-- _paginate: false -->

<br><br><br>

# Mulțumesc pentru atenție!

<br>

<div class="columns">
<div>

**UPGRADE** — platformă bioinformatică end-to-end
pentru supravegherea metagenomică a AMR

<br>

<span class="pill">MinIO Lakehouse</span>
<span class="pill">PostgreSQL 15 + PostGIS</span>
<span class="pill">Sanic + Redis + RQ</span>
<span class="pill">Nextflow DSL2</span>
<span class="pill">React 18</span>
<span class="pill">ONT PromethION</span>

</div>
<div>

**Universitatea Tehnică a Moldovei**
Facultatea de Calculatoare, Informatică și Microelectronică

<br>

*53 eșantioane reale procesate · 7 etape pipeline · 18 instrumente Docker*

</div>
</div>
