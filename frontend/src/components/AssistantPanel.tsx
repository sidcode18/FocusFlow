"use client";

import { useEffect, useRef, useState } from "react";
import { api, type AgentAction, type ChatResponse } from "@/lib/api";

interface Msg {
  role: "user" | "agent" | "system";
  text: string;
  mode?: "bedrock" | "mock";
  actions?: AgentAction[];
  error?: boolean;
}

const SUGGESTIONS = [
  "Add finish investor deck by Friday 5pm, review PR tomorrow 10am, and buy groceries today",
  "I missed my expense report, replan my day",
  "How am I doing?",
];

/* Web Speech API typings (the standard TS dom lib does not guarantee these). */
interface SRAlternative {
  transcript: string;
}
interface SRResult {
  isFinal: boolean;
  length: number;
  [index: number]: SRAlternative;
}
interface SRResultList {
  length: number;
  [index: number]: SRResult;
}
interface SREvent {
  resultIndex: number;
  results: SRResultList;
}
interface SRErrorEvent {
  error: string;
}
interface ISpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SREvent) => void) | null;
  onerror: ((e: SRErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type SRCtor = new () => ISpeechRecognition;

function getSpeechRecognition(): SRCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SRCtor;
    webkitSpeechRecognition?: SRCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function MicIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
    </svg>
  );
}

function SoundIcon({ off }: { off: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      {off ? (
        <line x1="23" y1="9" x2="17" y2="15" />
      ) : (
        <>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
        </>
      )}
      {off && <line x1="17" y1="9" x2="23" y2="15" />}
    </svg>
  );
}

export default function AssistantPanel({ onMutated }: { onMutated: () => void }) {
  const [tab, setTab] = useState<"chat" | "voice">("chat");
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "system",
      text: "Describe tasks in plain language. I can create, complete, delete and reschedule tasks, generate your schedule, and replan missed work.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(true);
  const recRef = useRef<ISpeechRecognition | null>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending, interim]);

  useEffect(() => {
    return () => {
      try {
        recRef.current?.abort();
      } catch {
        /* already stopped */
      }
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    };
  }, []);

  function speak(text: string) {
    if (!soundOn || typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const clean = text.replace(/[•✓✗]/g, "");
    const u = new SpeechSynthesisUtterance(clean);
    u.rate = 1.02;
    window.speechSynthesis.speak(u);
  }

  async function send(text: string, speakReply = false) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setMessages((m) => [...m, { role: "user", text: trimmed }]);
    setInput("");
    setInterim("");
    setSending(true);
    try {
      const res = await api<ChatResponse>("/api/chat", {
        method: "POST",
        body: JSON.stringify({ message: trimmed }),
      });
      setMessages((m) => [
        ...m,
        { role: "agent", text: res.reply, mode: res.mode, actions: res.actions },
      ]);
      if (speakReply) speak(res.reply);
      onMutated();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed";
      setMessages((m) => [...m, { role: "agent", text: msg, error: true }]);
      if (speakReply) speak(msg);
    } finally {
      setSending(false);
    }
  }

  function toggleListening() {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      setVoiceError("Voice input needs Chrome or Edge — typing works everywhere.");
      return;
    }
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = true;
    rec.onresult = (e) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          const finalText = r[0].transcript.trim();
          if (finalText) {
            setInterim("");
            void send(finalText, true);
          }
        } else {
          live += r[0].transcript;
        }
      }
      if (live) setInterim(live);
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setVoiceError("Microphone blocked — allow mic access and try again.");
      } else if (e.error !== "aborted" && e.error !== "no-speech") {
        setVoiceError("Voice recognition failed — try again or type instead.");
      }
    };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    setVoiceError(null);
    try {
      rec.start();
      setListening(true);
    } catch {
      setVoiceError("Could not start the microphone — try again.");
    }
  }

  return (
    <section className="card flex h-[560px] flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="font-display text-lg">Assistant</h2>
        <div className="flex items-center gap-2">
          {tab === "voice" && (
            <button
              className="btn !px-2"
              onClick={() => setSoundOn((v) => !v)}
              title={soundOn ? "Mute spoken replies" : "Speak replies aloud"}
              aria-pressed={!soundOn}
            >
              <SoundIcon off={!soundOn} />
            </button>
          )}
          <div className="flex rounded-sm border border-line p-0.5 text-xs">
            {(["chat", "voice"] as const).map((t) => (
              <button
                key={t}
                className={`rounded-sm px-2.5 py-1 font-medium ${
                  tab === t ? "bg-ink text-paper" : "text-ink-soft hover:bg-cream"
                }`}
                onClick={() => setTab(t)}
              >
                {t === "chat" ? "Chat" : "Voice"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((m, i) =>
          m.role === "system" ? (
            <p key={i} className="rounded-sm bg-cream px-3 py-2 text-xs text-ink-soft">
              {m.text}
            </p>
          ) : (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : ""}`}>
              <div
                className={`max-w-[85%] rounded-sm border px-3 py-2 text-sm ${
                  m.role === "user"
                    ? "border-ink bg-ink text-paper"
                    : m.error
                      ? "border-danger/40 bg-[#f7ecec] text-danger"
                      : "border-line bg-panel"
                }`}
              >
                {m.role === "agent" && m.mode && (
                  <span
                    className={`mb-1 mr-1 inline-block rounded-sm border px-1 py-px text-[9px] font-semibold uppercase tracking-wide ${
                      m.mode === "bedrock"
                        ? "border-good/40 text-good"
                        : "border-warn/40 text-warn"
                    }`}
                    title={
                      m.mode === "bedrock"
                        ? "Reply generated by Amazon Bedrock"
                        : "Deterministic mock response — not AI output"
                    }
                  >
                    {m.mode === "bedrock" ? "Bedrock" : "Mock"}
                  </span>
                )}
                <p className="whitespace-pre-wrap">{m.text}</p>
                {m.actions && m.actions.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-line pt-2">
                    {m.actions.map((a, j) => (
                      <li key={j} className="flex items-start gap-1.5 text-xs">
                        <span
                          className={`mt-0.5 font-mono text-[10px] ${
                            a.ok ? "text-good" : "text-danger"
                          }`}
                        >
                          {a.ok ? "✓" : "✗"}
                        </span>
                        <span className="text-ink-soft">
                          <span className="font-mono text-[10px] text-muted">{a.tool}</span>
                          {a.summary ? ` — ${a.summary}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )
        )}
        {(sending || interim) && (
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-accent" />
            {interim ? `“${interim}”` : "Working…"}
          </div>
        )}
      </div>

      <div className="border-t border-line px-4 py-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="rounded-full border border-line px-2.5 py-1 text-[11px] text-ink-soft transition-colors hover:border-accent hover:text-accent"
              onClick={() => send(s)}
              disabled={sending}
            >
              {s.length > 46 ? `${s.slice(0, 46)}…` : s}
            </button>
          ))}
        </div>
        {voiceError && <p className="mb-2 text-xs text-danger">{voiceError}</p>}
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          {tab === "voice" && (
            <button
              type="button"
              onClick={toggleListening}
              disabled={sending}
              className={`flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full border transition-colors ${
                listening
                  ? "border-danger bg-danger text-white"
                  : "border-line text-ink-soft hover:border-accent hover:text-accent"
              }`}
              title={listening ? "Stop listening" : "Speak"}
              aria-pressed={listening}
              aria-label={listening ? "Stop listening" : "Speak"}
            >
              <MicIcon />
            </button>
          )}
          <input
            className="input"
            placeholder={
              tab === "voice"
                ? "Or type e.g. 'replan my day'"
                : "e.g. Add finish deck by Friday 5pm and review PR tomorrow"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
          />
          <button className="btn btn-primary" type="submit" disabled={sending || !input.trim()}>
            Send
          </button>
        </form>
      </div>
    </section>
  );
}
