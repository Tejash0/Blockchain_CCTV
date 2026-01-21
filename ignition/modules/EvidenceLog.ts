import { buildModule } from "@nomicfoundation/hardhat-ignition/modules";

const EvidenceLogModule = buildModule("EvidenceLogModule", (m) => {
  // Deploy the EvidenceLog contract (no constructor arguments needed)
  const evidenceLog = m.contract("EvidenceLog");

  return { evidenceLog };
});

export default EvidenceLogModule;
