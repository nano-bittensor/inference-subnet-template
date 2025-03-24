# 🧠 Inference Subnet Template

![Bittensor](https://img.shields.io/badge/Bittensor-Subnet-blue)
![Status](https://img.shields.io/badge/Status-WIP-orange)

## 📋 Technical Design Document

Inference subnets enable validators to challenge miners and collect responses through two primary request flows:

1. **🤖 Synthetic Requests**: Validators generate artificial request payloads or reuse previous organic requests to challenge miners.
2. **🌐 Organic Requests**: Validators act as forwarders between users/applications and miners.

While existing templates like [Bittensor Subnet Template](https://github.com/opentensor/bittensor-subnet-template) provide basic validator-miner connections, they lack features necessary for inference at scale.

### ✨ Key Features

- **🏗️ Microservice Architecture**: Designed for scalability and maintainability
- **⚡ Efficient Redis Integration**: Optimized data storage and retrieval
- **🎯 Hybrid Scoring Mechanism**: Advanced miner evaluation system
- **🔌 Direct Substrate Interface**: No dependency on Bittensor SDK
- **🚦 Intelligent Rate-Limiting**: Efficient management between validators and miners
- **📊 Advanced Scoring System**: Hybrid scoring with dropout mechanisms
- **🔄 Complete Workflow**: Full integration from user/app ↔️ validator ↔️ miner
- **🚀 Scalable Deployment**: Easy launch and scaling of your inference subnet

This design is effectively used in production subnets including Subnet 18 (Cortex.t) and Subnet 47 (Condenses.ai). This repository provides a unified template that any developer can use to build their own inference subnet with similar architecture and capabilities.

## 🎯 Roadmap

- [ ] Release first version of inference subnet template
- [ ] Add comprehensive examples showcasing the template's versatility:
  - 🔮 LLM Inference
  - 🖼️ Image Generation
  - 📝 OCR Processing
  - 🕵️ AI Content Detection
  - 👁️ Object Recognition
  - 🔍 And more...
- [ ] Develop 🤖 Agentic Subnet Builder: A tool that transforms your conceptual ideas into fully-functional subnet implementations

## 📄 License
```
The MIT License (MIT)
Copyright © 2025 toilaluan
```

## 📚 References
- https://github.com/rayonlabs/fiber
- https://github.com/opentensor/bittensor-subnet-template