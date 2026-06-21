import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

import styles from "./ProcessingPage.module.css";

import { useJobWebSocket } from "@/hooks/useJobWebSocket";
import { useAppStore } from "@/stores/appStore";

const STEPS = [
  { key: "fetching_video", label: "Fetching video" },
  { key: "transcribing", label: "Transcribing audio" },
  { key: "extracting_locations", label: "Finding locations" },
  { key: "geocoding", label: "Geocoding places" },
  { key: "finalizing", label: "Building trip" },
];

function stepIndex(stepKey: string | undefined) {
  if (!stepKey) return -1;
  return STEPS.findIndex((s) => s.key === stepKey);
}

export default function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { status, wsState } = useJobWebSocket(jobId ?? null);
  const { guestJob, setGuestJob } = useAppStore();

  // Redirect to map when completed
  useEffect(() => {
    if (status?.status === "completed") {
      // In Phase 3 the worker will return a tripId; for now navigate to demo
      const tripId = (status as any).tripId ?? "demo";
      if (guestJob) setGuestJob({ ...guestJob, tripId });
      setTimeout(() => navigate(`/trips/${tripId}`), 600);
    }
  }, [status, navigate, guestJob, setGuestJob]);

  const activeStep = stepIndex(status?.currentStep);
  const progress = status?.progress ?? 0;
  const failed = status?.status === "failed";

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Animated icon */}
        <div className={styles.iconWrap}>
          <div className={`${styles.icon} ${failed ? styles.failed : ""}`}>
            {failed ? "✕" : "◈"}
          </div>
          {!failed && <div className={styles.iconRing} />}
        </div>

        <h1 className={styles.title}>{failed ? "Processing failed" : "Extracting your trip…"}</h1>

        {failed ? (
          <div className={styles.errorBox}>
            <p>{status?.error ?? "An unexpected error occurred."}</p>
            <button className={styles.retryBtn} onClick={() => navigate("/")}>
              Try a different URL
            </button>
          </div>
        ) : (
          <>
            {/* Overall progress bar */}
            <div className={styles.progressTrack}>
              <div className={styles.progressFill} style={{ width: `${progress}%` }} />
            </div>
            <p className={styles.progressPct}>{progress}%</p>

            {/* Per-step indicators */}
            <div className={styles.steps}>
              {STEPS.map((step, i) => {
                const done = i < activeStep || progress === 100;
                const active = i === activeStep && progress < 100;
                return (
                  <div
                    key={step.key}
                    className={`${styles.step} ${done ? styles.done : ""} ${active ? styles.active : ""}`}
                  >
                    <div className={styles.stepDot}>
                      {done ? "✓" : active ? <span className={styles.pulse} /> : null}
                    </div>
                    <span>{step.label}</span>
                  </div>
                );
              })}
            </div>

            {status?.progressMessage && <p className={styles.message}>{status.progressMessage}</p>}

            {wsState === "error" && <p className={styles.wsNote}>Using polling fallback…</p>}
          </>
        )}
      </div>
    </div>
  );
}
