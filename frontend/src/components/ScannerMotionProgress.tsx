import { scannerMotionSteps } from "./scannerProgress";

type Props = {
  status: string | undefined;
  stage: string | undefined;
  details: Record<string, unknown>;
};

const LABELS: Record<string, string> = {
  waiting: "대기",
  active: "진행 중",
  done: "완료",
  failed: "실패",
  cancelled: "중단",
};

/** Pure presentation: the Backend job is the only source of phase truth. */
export default function ScannerMotionProgress({ status, stage, details }: Props) {
  const steps = scannerMotionSteps(status, stage, details);
  return (
    <div className="scanner-motion-progress" aria-label="종목 찾기 진행 단계">
      <ol className="scanner-motion-steps">
        {steps.map((step, index) => (
          <li className={"scanner-motion-step " + step.status} key={step.id}>
            <div className="scanner-motion-step-track">
              <span className="scanner-motion-step-dot" aria-hidden="true">
                {step.status === "done" ? "✓" : step.status === "failed" ? "!" : step.status === "cancelled" ? "–" : index + 1}
              </span>
              {index < steps.length - 1 && <span className="scanner-motion-step-line" aria-hidden="true" />}
            </div>
            <strong>{step.label}</strong>
            <small>{LABELS[step.status]}</small>
          </li>
        ))}
      </ol>
    </div>
  );
}
