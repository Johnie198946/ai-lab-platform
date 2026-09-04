// Build-only entry: expose the exact Hermes shared Gateway implementation to
// the standalone showroom page without copying or reimplementing its protocol.
export {
  JsonRpcGatewayClient,
  buildHermesWebSocketUrl,
  skillInvocationText,
} from "../../apps/shared/src/index.ts";
