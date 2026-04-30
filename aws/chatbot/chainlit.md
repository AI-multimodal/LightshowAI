# AmSC LightshowAI

**XANES analysis assistant.** Predict K-edge X-ray absorption near-edge structure spectra and visualize crystal structures, end-to-end, from a single chat.

Powered by:
- **OmniXAS** neural networks via the [LightshowAI](https://github.com/AI-multimodal/LightshowAI) MCP server (BNL)
- **Materials Project** structure database via the `mp_api` MCP server
- **Claude** large-language-model agent (via the AmSC i2 LiteLLM gateway)

## What it can do

- Search Materials Project for crystal structures by formula, chemical system, or oxidation state
- Render rotatable 3D crystal viewers inline in the chat
- Predict K-edge XANES (FEFF for Co, Cr, Cu, Fe, Mn, Ni, Ti, V; VASP for Ti and Cu)
- Compare predicted spectra across multiple polymorphs with shift-optimized Pearson, Spearman, and Cos(∂) metrics
- Save plots and structure HTML to `~/tmp/` for inline display

## Try it

> *Show the structure of mp-2657 and predict its Ti K-edge XANES with FEFF.*

> *Compare Ti K-edge XANES for the three TiO₂ polymorphs (rutile, anatase, brookite).*

> *Search Materials Project for stable Cu oxides and predict their Cu K-edge XANES.*

## Acknowledgments

LightshowAI: Carbone, Lu, Kelly, Sri Vatsavai, Qu, Cao, Jiang (BNL).
References: [Phys. Rev. Mater. 8, 013801 (2024)], [JOSS 8(87), 5182 (2023)], [Phys. Rev. Mater. 9, 043803 (2025)].

---

Agentic workflows empowered by **AmSC AI Services** and **AmSC Model Services**.
For questions, please contact Huihuo Zheng at [huihuo.zheng@anl.gov](mailto:huihuo.zheng@anl.gov).
