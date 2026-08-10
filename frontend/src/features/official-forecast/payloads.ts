import type {
  ExecutiveSummaryEnvelope,
  LatestRunResponse,
  ModelPerformanceEnvelope,
  PlcEnvelope,
  QaEnvelope,
  QuantityEnvelope,
  RevenueEnvelope,
  WholesaleEnvelope,
} from "./contract";

export type BrandPayload = {
  executive: ExecutiveSummaryEnvelope;
  revenue: RevenueEnvelope;
  quantity: QuantityEnvelope;
  wholesale: WholesaleEnvelope;
};

export type GovernancePayload = {
  performance: ModelPerformanceEnvelope;
  qa: QaEnvelope;
  latest: LatestRunResponse;
};

export type OutputPayload = {
  latest: LatestRunResponse;
  executive: ExecutiveSummaryEnvelope;
  revenue: RevenueEnvelope;
  quantity: QuantityEnvelope;
  plc: PlcEnvelope;
  wholesale: WholesaleEnvelope;
  performance: ModelPerformanceEnvelope;
  qa: QaEnvelope;
};
