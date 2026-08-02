import type { ReactNode } from "react";

export type VoiceCaptureState =
  | "idle"
  | "requesting-permission"
  | "recording"
  | "transcribing"
  | "ready"
  | "error";

export type SpeechPlaybackState = "idle" | "loading" | "playing" | "error";

export type VoiceProviderOption = {
  provider: string;
  model: string;
  configured?: boolean;
  cloud?: boolean;
  demo?: boolean;
};

export type VoiceSessionTimelineItem = {
  id: string;
  status: string;
  provider: string;
  model: string;
  createdAt: string;
  durationMs?: number | null;
  audioSizeBytes?: number | null;
  traceId?: string | null;
};

type VoiceInputButtonProps = {
  state: VoiceCaptureState;
  mode: "click" | "push";
  disabled?: boolean;
  onToggle?: () => void;
  onPressStart?: () => void;
  onPressEnd?: () => void;
  icon?: ReactNode;
};

export function VoiceInputButton({
  state,
  mode,
  disabled = false,
  onToggle,
  onPressStart,
  onPressEnd,
  icon,
}: VoiceInputButtonProps) {
  const recording = state === "recording";
  return (
    <button
      className={`voice-input-button voice-input-button--${state}`}
      type="button"
      aria-label={recording ? "Stop recording" : "Start voice recording"}
      aria-pressed={recording}
      disabled={disabled}
      title={mode === "push" ? "Hold to speak" : "Start or stop recording"}
      onClick={mode === "click" ? onToggle : undefined}
      onPointerDown={mode === "push" ? onPressStart : undefined}
      onPointerUp={mode === "push" ? onPressEnd : undefined}
      onPointerCancel={mode === "push" ? onPressEnd : undefined}
      onKeyDown={(event) => {
        if (mode === "push" && event.code === "Space" && !recording) {
          event.preventDefault();
          onPressStart?.();
        }
      }}
      onKeyUp={(event) => {
        if (mode === "push" && event.code === "Space") {
          event.preventDefault();
          onPressEnd?.();
        }
      }}
    >
      {icon ? <span aria-hidden="true">{icon}</span> : null}
      <span>{recording ? "Stop" : mode === "push" ? "Hold" : "Record"}</span>
    </button>
  );
}

type VoiceRecorderProps = {
  state: VoiceCaptureState;
  elapsedSeconds: number;
  maxSeconds: number;
  level: number;
  children?: ReactNode;
};

export function VoiceRecorder({
  state,
  elapsedSeconds,
  maxSeconds,
  level,
  children,
}: VoiceRecorderProps) {
  return (
    <section
      className={`voice-recorder voice-recorder--${state}`}
      aria-label="Voice recorder"
    >
      <RecordingIndicator
        state={state}
        elapsedSeconds={elapsedSeconds}
        maxSeconds={maxSeconds}
      />
      <AudioLevelMeter level={level} active={state === "recording"} />
      {children}
    </section>
  );
}

export function RecordingIndicator({
  state,
  elapsedSeconds,
  maxSeconds,
}: {
  state: VoiceCaptureState;
  elapsedSeconds: number;
  maxSeconds: number;
}) {
  const remaining = Math.max(maxSeconds - elapsedSeconds, 0);
  return (
    <div className="recording-indicator" aria-live="polite">
      <span className="recording-indicator__dot" aria-hidden="true" />
      <span>{stateLabel(state)}</span>
      <span className="recording-indicator__time">
        {formatSeconds(elapsedSeconds)} / {formatSeconds(maxSeconds)}
      </span>
      {state === "recording" ? (
        <span className="recording-indicator__remaining">
          {formatSeconds(remaining)} left
        </span>
      ) : null}
    </div>
  );
}

export function AudioLevelMeter({
  level,
  active = true,
}: {
  level: number;
  active?: boolean;
}) {
  const normalized = Math.max(0, Math.min(level, 1));
  return (
    <div className="audio-level-meter" aria-label="Input level">
      {Array.from({ length: 12 }).map((_, index) => {
        const filled = active && index / 12 <= normalized;
        return (
          <span
            key={index}
            className={
              filled
                ? "audio-level-meter__bar is-active"
                : "audio-level-meter__bar"
            }
            style={{ blockSize: `${24 + index * 4}%` }}
          />
        );
      })}
    </div>
  );
}

export function TranscriptPreview({
  text,
  editable,
  onEdit,
  onRetry,
  onDiscard,
  onSend,
}: {
  text: string;
  editable: boolean;
  onEdit?: () => void;
  onRetry?: () => void;
  onDiscard?: () => void;
  onSend?: () => void;
}) {
  return (
    <section className="transcript-preview" aria-label="Transcript preview">
      <p>{text || "No transcript yet."}</p>
      <div className="voice-action-row">
        {editable ? (
          <button type="button" onClick={onEdit}>
            Edit
          </button>
        ) : null}
        <button type="button" onClick={onRetry}>
          Retry
        </button>
        <button type="button" onClick={onDiscard}>
          Discard
        </button>
        <button
          className="command-button"
          type="button"
          onClick={onSend}
          disabled={!text.trim()}
        >
          Send
        </button>
      </div>
    </section>
  );
}

export function TranscriptEditor({
  value,
  onChange,
  onCancel,
  onSend,
}: {
  value: string;
  onChange: (value: string) => void;
  onCancel?: () => void;
  onSend?: () => void;
}) {
  return (
    <section className="transcript-editor" aria-label="Edit transcript">
      <label>
        Transcript
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <div className="voice-action-row">
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="command-button" type="button" onClick={onSend}>
          Send Transcript
        </button>
      </div>
    </section>
  );
}

export function VoiceModeToggle({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <label className="voice-mode-toggle">
      <input
        type="checkbox"
        checked={enabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>Voice mode</span>
    </label>
  );
}

export function SpeechPlaybackControls({
  state,
  onPlay,
  onStop,
}: {
  state: SpeechPlaybackState;
  onPlay?: () => void;
  onStop?: () => void;
}) {
  return (
    <div
      className={`speech-playback-controls speech-playback-controls--${state}`}
    >
      <button
        type="button"
        onClick={onPlay}
        disabled={state === "loading" || state === "playing"}
      >
        Play
      </button>
      <button
        type="button"
        onClick={onStop}
        disabled={state !== "playing" && state !== "loading"}
      >
        Stop
      </button>
      <span aria-live="polite">{playbackLabel(state)}</span>
    </div>
  );
}

export function VoiceSettingsPanel({
  stt,
  tts,
  transcriptReviewEnabled,
  autoSpeakAssistant,
  retainRawAudio,
  onTranscriptReviewChange,
  onAutoSpeakChange,
  onRetainAudioChange,
}: {
  stt: VoiceProviderOption;
  tts: VoiceProviderOption;
  transcriptReviewEnabled: boolean;
  autoSpeakAssistant: boolean;
  retainRawAudio: boolean;
  onTranscriptReviewChange?: (enabled: boolean) => void;
  onAutoSpeakChange?: (enabled: boolean) => void;
  onRetainAudioChange?: (enabled: boolean) => void;
}) {
  return (
    <section className="voice-settings-panel" aria-label="Voice settings">
      <VoiceProviderBadge option={stt} label="STT" />
      <VoiceProviderBadge option={tts} label="TTS" />
      <label>
        <input
          type="checkbox"
          checked={transcriptReviewEnabled}
          onChange={(event) => onTranscriptReviewChange?.(event.target.checked)}
        />
        Review transcript
      </label>
      <label>
        <input
          type="checkbox"
          checked={autoSpeakAssistant}
          onChange={(event) => onAutoSpeakChange?.(event.target.checked)}
        />
        Speak answers
      </label>
      <label>
        <input
          type="checkbox"
          checked={retainRawAudio}
          onChange={(event) => onRetainAudioChange?.(event.target.checked)}
        />
        Retain audio
      </label>
    </section>
  );
}

export function VoiceProviderBadge({
  option,
  label,
}: {
  option: VoiceProviderOption;
  label?: string;
}) {
  const tone = option.demo ? "demo" : option.cloud ? "cloud" : "local";
  return (
    <span className={`voice-provider-badge voice-provider-badge--${tone}`}>
      {label ? `${label}: ` : null}
      {option.provider} / {option.model}
      {option.configured === false ? " (not configured)" : null}
    </span>
  );
}

export function VoiceSessionTimeline({
  items,
  onOpen,
}: {
  items: VoiceSessionTimelineItem[];
  onOpen?: (id: string) => void;
}) {
  return (
    <ol className="voice-session-timeline" aria-label="Voice session timeline">
      {items.map((item) => (
        <li key={item.id}>
          <button type="button" onClick={() => onOpen?.(item.id)}>
            <span>{item.status}</span>
            <strong>{item.provider}</strong>
            <small>
              {item.model} · {formatOptionalMs(item.durationMs)} ·{" "}
              {formatOptionalBytes(item.audioSizeBytes)}
            </small>
          </button>
        </li>
      ))}
    </ol>
  );
}

export function MicrophonePermissionNotice({
  state,
}: {
  state: VoiceCaptureState;
}) {
  if (state !== "requesting-permission" && state !== "error") {
    return null;
  }
  return (
    <p
      className="microphone-permission-notice"
      role={state === "error" ? "alert" : "status"}
    >
      {state === "error"
        ? "Microphone access failed or was denied."
        : "The browser is asking for microphone permission."}
    </p>
  );
}

export function AudioPrivacyNotice({
  provider,
  retainRawAudio,
}: {
  provider: string;
  retainRawAudio: boolean;
}) {
  return (
    <p className="audio-privacy-notice">
      {provider === "mock"
        ? "Demo transcription is deterministic and local to the app."
        : "Audio is sent to the configured server-side speech provider."}{" "}
      {retainRawAudio
        ? "Raw audio retention is enabled."
        : "Raw audio is not retained."}
    </p>
  );
}

function stateLabel(state: VoiceCaptureState) {
  if (state === "requesting-permission") {
    return "Requesting microphone";
  }
  if (state === "recording") {
    return "Recording";
  }
  if (state === "transcribing") {
    return "Transcribing";
  }
  if (state === "ready") {
    return "Transcript ready";
  }
  if (state === "error") {
    return "Voice error";
  }
  return "Idle";
}

function playbackLabel(state: SpeechPlaybackState) {
  if (state === "loading") {
    return "Preparing speech";
  }
  if (state === "playing") {
    return "Playing";
  }
  if (state === "error") {
    return "Playback error";
  }
  return "Speech idle";
}

function formatSeconds(value: number) {
  const safe = Math.max(0, Math.round(value));
  const minutes = Math.floor(safe / 60);
  const seconds = String(safe % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function formatOptionalMs(value?: number | null) {
  if (value === null || value === undefined) {
    return "duration unknown";
  }
  return `${Math.round(value / 1000)}s`;
}

function formatOptionalBytes(value?: number | null) {
  if (value === null || value === undefined) {
    return "size unknown";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  return `${Math.round(value / 1024)} KB`;
}
