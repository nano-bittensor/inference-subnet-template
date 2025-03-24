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

## ➕ ✖️ Addiction and Multiplication Subnet

This is a simple example of an inference subnet that uses the template to build a subnet for addition and multiplication.
Validator will send 2 random numbers to the miner and the miner will return the result of the addition ➕ or multiplication ✖️ of the two numbers.

## 🚀 Getting Started

**Clone the repository**

```bash
git clone https://github.com/nano-bittensor/inference-subnet-template
cd inference-subnet-template
pip install uv
uv venv
. .venv/bin/activate
uv sync
```

#### Miner

1. Start server. Ensure the port is publicly accessible.

```bash
uvicorn inference_subnet.neurons.miner.app:app --host 0.0.0.0 --port 8000
```

2. Register server address to blockchain.

```bash
python inference_subnet/neurons/miner/submit_server_address.py \
--wallet-hotkey <hotkey> \
--wallet-name <name> \
--wallet-path "~/.bittensor/wallets" \
--netuid 1 \
--network finney \
--external-ip <ip> \
--external-port 8000
```

#### Validator

1. Configure Environment Variables

```bash
export WALLET.NAME=<name>
export WALLET.PATH="~/.bittensor/wallets"
export SUBSTRATE_SIDECAR.NETUID=1
```

2. Start Validator Services

| Service Name               | Command                                                                 |
|----------------------------|-------------------------------------------------------------------------|
| `sidecar_subtensor_service`| `uvicorn inference_subnet.services.sidecar_subtensor.app:app --host 0.0.0.0 --port 9001` |
| `managing_service`         | `uvicorn inference_subnet.services.managing.app:app --host 0.0.0.0 --port 9002`         |
| `scoring_service`          | `uvicorn inference_subnet.services.scoring.app:app --host 0.0.0.0 --port 9003`          |
| `synthesizing_service`     | `uvicorn inference_subnet.services.synthesizing.app:app --host 0.0.0.0 --port 9004`     |

3. Start `validating-orchestrator`

```bash
python inference_subnet/neurons/validator/main.py
```

## 📄 License
```
The MIT License (MIT)
Copyright © 2025 toilaluan
```

## 📚 References
- https://github.com/rayonlabs/fiber
- https://github.com/opentensor/bittensor-subnet-template