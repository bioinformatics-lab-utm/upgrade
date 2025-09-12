# UPGRADE - Urban Pathogen Genomic Surveillance Network

## Project Overview

The UPGRADE project establishes a dynamic Romanian-Moldovan research collaboration focused on rapid pathogen identification and real-time genomic surveillance in complex urban environments. This project integrates expertise across data generation and bioinformatics analysis to monitor antimicrobial resistance (AMR) genes and pathogens from diverse environmental sources.

## Grant Information

- **Project Title:** Metagenomics and Bioinformatics tools for environmental genomic surveillance of pathogens and antimicrobial resistance genes in public spaces
- **Duration:** 24 months
- **Coordinator:** "Ștefan cel Mare" University of Suceava (USV), Romania
- **Partner:** Technical University of Moldova (TUM)
- **Funding Program:** Romanian-Moldovan bilateral research collaboration

## Research Objectives

### Primary Scope
Foster a dynamic Romanian-Moldovan research collaboration focusing on rapid pathogen identification and real-time genomic surveillance in complex urban environments.

### Specific Aims

**Aim 1:** Sample collection and creating a comprehensive approach to streamline laboratory methods for complex environmental surveillance
- Systematic sample collection from university campuses
- Environmental metadata collection (temperature, humidity, coordinates, timing)
- Streamlined laboratory workflows using Oxford Nanopore Technology (ONT)

**Aim 2:** Development of a scalable and modular bioinformatics framework for high-throughput environmental genomic surveillance
- Quality control and assembly pipelines
- Pathogen detection and antimicrobial resistance gene (ARG) identification
- Integration with environmental metadata

**Aim 3:** Establish a regional community-oriented platform for environmental genomic surveillance of pathogens
- UP-GEN (Urban Pathogen Genomic Surveillance Network) platform
- Interactive tools for data exploration and visualization
- Community engagement and public health integration

## Technical Architecture

![UPGRADE Project Architecture](docs/UPGRADE_Architecture.png)

*System architecture showing data flows from weather APIs and genomic files through the bioinformatics pipeline to analytics dashboards.*

### Technology Stack
- **Data Storage:** PostgreSQL with PostGIS, MinIO Object Storage
- **Pipeline Orchestration:** Apache Airflow, Nextflow
- **Message Streaming:** Apache Kafka
- **Bioinformatics Tools:** NanoPlot, Filtlong, Flye, Kraken2, Abricate
- **Visualization:** Streamlit, React Dashboard
- **Infrastructure:** Docker Compose

### Data Processing Workflow
1. **Quality Control** - NanoPlot quality assessment, Filtlong read filtering
2. **Assembly** - Flye for long-read metagenomic assembly
3. **Taxonomic Classification** - Kraken2, Sourmash
4. **AMR Detection** - Abricate against CARD database
5. **Environmental Correlation** - Weather data integration

## Repository Structure

```
upgrade/
├── airflow/                      # Workflow orchestration
│   ├── dags/                     # Pipeline definitions
│   ├── plugins/                  # Custom operators
│   └── config/                   # Configuration files
├── nextflow/                     # Bioinformatics pipelines
│   ├── main.nf                   # Main pipeline
│   ├── modules/                  # Pipeline modules
│   └── nextflow.config           # Pipeline configuration
├── streamlit/                    # Web dashboard
│   ├── app.py                    # Main application
│   └── airflow_integration.py   # Pipeline integration
├── kafka/                        # Data streaming
│   ├── producer/                 # Weather data producer
│   └── consumer/                 # Data consumer
├── database/
│   └── migrations/               # Database schema
├── docs/                         # Project documentation
├── sandbox/                      # Development experiments
└── web-dashboard/                # React frontend
    ├── backend/                  # API backend
    └── frontend/                 # React components
```

## Development Status

This project is currently in active development. The infrastructure includes:

- **Containerized Environment:** Docker Compose setup with PostgreSQL, MinIO, Redis, Airflow, Kafka
- **Weather Data Pipeline:** Real-time weather data collection and storage
- **Genomic Processing:** Nextflow pipeline with quality control modules
- **Web Interface:** Streamlit dashboard for data visualization

## Team

### Romania (USV)
- **Project Director:** Dr. Roxana Filip - Microbiology and bacterial resistance mechanisms
- **Senior Researcher:** Prof. Mihai Dimian - Mathematical models and biostatistics
- **Postdoc Researcher:** Dr. Liliana Anchidin-Norocel - Metagenomics expertise

### Moldova (TUM)
- **Co-Director:** Dr. Inna Rastimesina - Environmental microbiology and biotechnology
- **Senior Researcher:** Dr. Dumitru Ciorbă - Computational biology and bioinformatics
- **PhD Student:** Viorel Munteanu - Bioinformatics and data analysis
- **PhD Student:** Eugeniu Catlabuga - Software engineering and platform development

## Publications and Dissemination

### Planned Publications
- Two high-impact Q1/Q2 journal publications
- Conference presentations at RoBioinfo, ECCO2026, ESCMID

### Platform Deployment
- UP-GEN platform development
- Integration with ELIXIR platform
- Community engagement activities

## Contact Information

**Project Coordinator:** Dr. Roxana Filip  
Email: roxana.filip@usv.ro  
Institution: "Ștefan cel Mare" University of Suceava, Romania

**Technical Lead:** Viorel Munteanu  
Email: viorel.munteanu@utm.md  
Institution: Technical University of Moldova

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This work is supported by the Romanian-Moldovan bilateral research collaboration grant program. We acknowledge the contributions of all team members and the support from both participating institutions.