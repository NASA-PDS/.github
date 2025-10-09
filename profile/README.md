# 🌌 NASA Planetary Data System (PDS)

Welcome to the **NASA Planetary Data System (PDS)** GitHub organization —  
the home for open-source software that powers NASA’s planetary science data archiving, management, and discovery ecosystem.

PDS serves as the **official archive for all NASA planetary mission data**, ensuring long-term preservation, accessibility, and usability for the global science community. This organization hosts the tools, services, standards, and infrastructure that enable that mission.

---

## 🚀 Overview

The **PDS Engineering Node (EN)** at the Jet Propulsion Laboratory (JPL) leads the design, development, and integration of the PDS software ecosystem, in collaboration with NASA’s discipline nodes and international partners.  
Our software and standards form the foundation for the **Planetary Data Ecosystem (PDE)** and the evolving **Planetary Data Cloud**.

### Core Principles

- **Open Science** — All tools and standards are open-source, publicly developed, and freely accessible.  
- **Interoperability** — Built on the PDS4 Information Model, enabling consistent metadata and seamless data integration.  
- **FAIR Data** — Ensuring data are Findable, Accessible, Interoperable, and Reusable.  
- **Automation & Cloud Readiness** — Designed for scalable, cloud-native operations and efficient data workflows.

---

## 🧩 Key Components

| Category | Repositories | Description |
|-----------|---------------|-------------|
| **Core Standards** | [`pds4-information-model`](https://github.com/NASA-PDS/pds4-information-model), [`ldd-manager`](https://github.com/NASA-PDS/ldd-manager) | PDS4 schema, common dictionary, and local data dictionary tools. |
| **Validation & Stewardship** | [`validate`](https://github.com/NASA-PDS/validate), [`deep-archive`](https://github.com/NASA-PDS/deep-archive) | Tools for verifying and preserving data and metadata compliance. |
| **Registry & Search Services** | [`registry`](https://github.com/NASA-PDS/registry), [`registry-api`](https://github.com/NASA-PDS/registry-api), [`registry-harvest`](https://github.com/NASA-PDS/registry-harvest) | Distributed catalog and API services built on OpenSearch Serverless. |
| **Data Services Platform** | [`nucleus`](https://github.com/NASA-PDS/nucleus), [`data-upload-manager`](https://github.com/NASA-PDS/data-upload-manager) | Cloud-based data processing, upload, and pipeline orchestration tools. |
| **Web & UX** | [`pds-engineering`](https://github.com/NASA-PDS/pds-engineering), [`feedback-widget`](https://github.com/NASA-PDS/feedback-widget), [`pds-wds-web`](https://github.com/NASA-PDS/pds-wds-web) | Web modernization and unified UX for PDS nodes and portals. |
| **APIs & Clients** | [`pds-api`](https://github.com/NASA-PDS/pds-api), [`pds4-tools`](https://github.com/NASA-PDS/pds4-tools) | REST and Python interfaces for searching and accessing PDS data. |
| **Infrastructure & Ops** | [`terraform-pds-cloud`](https://github.com/NASA-PDS/terraform-pds-cloud), [`aws-cloudops`](https://github.com/NASA-PDS/aws-cloudops) | Terraform modules and automation for Planetary Data Cloud deployments. |
| **Community & Governance** | [`pds-github-org`](https://github.com/NASA-PDS/pds-github-org), [`pds-doi-service`](https://github.com/NASA-PDS/pds-doi-service), [`pds-swg`](https://github.com/NASA-PDS/pds-swg) | Governance, DOI management, and working-group coordination. |

---

## ☁️ Planetary Data Cloud

The **Planetary Data Cloud (PDC)** is our next-generation architecture hosted on AWS.  
It unifies data access, registry, and analysis services into a scalable, interoperable platform.

Core services include:
- **Registry** — Centralized metadata catalog with federated search.
- **Data Upload Manager** — Streamlined submission workflows for missions and nodes.
- **Nucleus** — Workflow and data pipeline orchestration.
- **PDS API** — Standard REST API for all data discovery and access.

---

## 🧪 Developer Guidelines

We follow modern software engineering practices across all repositories:

- **Branching & CI/CD** — Feature branches, pull-request reviews, automated builds via GitHub Actions.
- **Testing** — Unit, integration, and regression tests required for all PRs.
- **Documentation** — Every service and tool includes usage docs and API specs.
- **Releases** — Managed through [GitHub Projects and Milestones](https://github.com/orgs/NASA-PDS/projects); see `releases/current` for the latest system build.

See [`copilot-instructions.md`](https://github.com/NASA-PDS/copilot-instructions.md) for PR review standards.

For more developer documentation and best practices, visit the [NASA-PDS Wiki](https://github.com/NASA-PDS/nasa-pds.github.io/wiki).

---

## 📚 Resources

- [🌐 PDS Engineering Node](https://pds-engineering.jpl.nasa.gov)
- [🔍 PDS Data Portal](https://pds.nasa.gov)
- [📖 PDS4 Standards Reference](https://pds.nasa.gov/pds4/)
- [📘 Developer Docs]([https://nasa-pds.github.io/](https://github.com/NASA-PDS/nasa-pds.github.io/wiki))
- [🧠 Planetary Data Ecosystem IRB Report (2021)](https://science.nasa.gov/files/science-pink/s3fs-public/atoms/files/PDE%20IRB%20Final%20Report.pdf)

---

## 🤝 Contributing

We welcome community collaboration!  
Before submitting a pull request:
1. Open or reference an issue.
2. Follow the [Contributor Guidelines](https://github.com/NASA-PDS/.github/blob/main/CONTRIBUTING.md).
3. Ensure tests and docs are updated.
4. Request review from the appropriate working group or module owner.

---

## 📬 Contact

- **General Inquiries / Help Desk:** [pds_operator@jpl.nasa.gov](mailto:pds_operator@jpl.nasa.gov)  
- **Report Issues:** via the relevant GitHub repository or [PDS Help Desk](https://pds.nasa.gov/?feedback=true)  
- **Security:** See [SECURITY.md](https://github.com/NASA-PDS/.github/blob/main/SECURITY.md)

---

## 🛰️ Acknowledgments

This GitHub organization includes contributions from multiple **NASA Planetary Data System Nodes**, each responsible for a scientific discipline or technical function.  
The **PDS Engineering Node (EN)**, operated at the **Jet Propulsion Laboratory, California Institute of Technology**, manages the overall GitHub organization, ensuring system-wide interoperability, software quality, and cloud operations.  

The PDS is sponsored by NASA’s **Science Mission Directorate** and supported by the global planetary science community.

---
