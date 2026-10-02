import { useEffect, useRef, useState } from "react";
import { api, json } from "./api.ts";
import type { Post, TranslationJob, TranslationStatus } from "./types";
import { initialReadingChinese } from "./workspaceLogic.ts";

export function translatedPost(
  item: Post,
  chinese: boolean,
  model: string,
): Post {
  if (!chinese || !translationReady(item, model)) return item;
  return {
    ...item,
    title: item.translation!.title,
    content: item.translation!.content,
    summary: item.translation!.summary,
  };
}

export function translationReady(item: Post, model: string) {
  return (
    !!item.translation &&
    item.translation.language === "zh" &&
    (item.translation.cache_key || item.translation.model) === model
  );
}

export function sameOriginal(left: Post, right: Post) {
  return (
    left.id === right.id &&
    left.title === right.title &&
    left.content === right.content &&
    left.summary === right.summary
  );
}

export function useChineseTranslation(
  items: Post[],
  apply: (items: Post[]) => void,
) {
  const [chinese, setChinese] = useState(
    () => initialReadingChinese(localStorage.getItem("radar-reading-language")),
  );
  const [configuration, setConfiguration] = useState<TranslationStatus | null>(
    null,
  );
  const [running, setRunning] = useState(false);
  const [completed, setCompleted] = useState(0);
  const [issue, setIssue] = useState("");
  const [failures, setFailures] = useState<Record<string, string>>({});
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const failedVersions = useRef(
    new Map<string, { revision: string; model: string; message: string }>(),
  );
  const version = (item: Post) =>
    JSON.stringify([item.title, item.content, item.summary]);
  // Bookmark and read changes do not start another translation request.
  const revision = JSON.stringify(
    items.map((item) => [item.id, item.title, item.content, item.summary]),
  );
  const snapshot = useRef(items);
  snapshot.current = items;

  useEffect(() => {
    localStorage.setItem("radar-reading-language", chinese ? "zh" : "original");
  }, [chinese]);

  useEffect(() => {
    const controller = new AbortController();
    void api<TranslationStatus>("/translation/status", { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setConfiguration(result); })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let resolveDelay: (() => void) | undefined;
    const delay = () =>
      new Promise<void>((resolve) => {
        resolveDelay = resolve;
        timer = setTimeout(resolve, 1000);
      });
    const active = () =>
      current === generation.current && !controller.signal.aborted;
    setRunning(false);
    setIssue("");
    setFailures({});
    if (chinese && snapshot.current.length) {
      setRunning(true);
      void (async () => {
        try {
          const config = await api<TranslationStatus>("/translation/status", {
            signal: controller.signal,
          });
          if (!active()) return;
          setConfiguration(config);
          if (!config.configured) {
            setIssue(
              config.message ||
                "服务未检测到 DeepSeek 环境变量，请配置后重启网站。",
            );
            return;
          }
          const blocked: Record<string, string> = {};
          const pending = snapshot.current.filter((item) => {
            if (translationReady(item, config.cache_key || config.model)) return false;
            const failure = failedVersions.current.get(item.id);
            if (
              failure?.revision === version(item) &&
              failure.model === (config.cache_key || config.model)
            ) {
              blocked[item.id] = failure.message;
              return false;
            }
            return true;
          });
          setFailures(blocked);
          let successful = snapshot.current.filter((item) =>
            translationReady(item, config.cache_key || config.model),
          ).length;
          setCompleted(successful);
          for (
            let offset = 0;
            offset < pending.length && active();
            offset += 60
          ) {
            const batch = pending.slice(offset, offset + 60);
            let job = await api<TranslationJob>("/translate", {
              ...json("POST", {
                ids: batch.map((item) => item.id),
                target_language: "zh",
              }),
              signal: controller.signal,
            });
            const started = Date.now();
            while (job.status === "running" && active()) {
              if (Date.now() - started > 30 * 60_000)
                throw new Error("翻译仍在后台处理，稍后可重试读取结果。");
              await delay();
              if (!active()) return;
              job = await api<TranslationJob>(`/translation/jobs/${job.id}`, {
                signal: controller.signal,
              });
              if (active()) setCompleted(successful + job.completed);
            }
            if (!active()) return;
            if (job.items) apply(job.items);
            successful += job.completed;
            setCompleted(successful);
            if (job.errors.length) {
              for (const error of job.errors) {
                const original = batch.find((item) => item.id === error.id);
                if (original)
                  failedVersions.current.set(error.id, {
                    revision: version(original),
                    model: config.cache_key || config.model,
                    message: error.message,
                  });
                else setIssue(error.message);
              }
              setFailures((previous) => ({
                ...previous,
                ...Object.fromEntries(
                  job.errors
                    .filter((error) =>
                      batch.some((item) => item.id === error.id),
                    )
                    .map((error) => [error.id, error.message]),
                ),
              }));
            }
            if (job.status === "failed" && !job.errors.length)
              setIssue("本次翻译未完成，原文已保留，可点击重试。");
          }
        } catch (error) {
          if (active())
            setIssue(
              error instanceof Error
                ? error.message
                : "暂时无法翻译，请稍后重试。",
            );
        } finally {
          if (active()) setRunning(false);
        }
      })();
    }
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
      resolveDelay?.();
    };
  }, [chinese, revision, retry, apply]);

  const model = configuration?.cache_key || configuration?.model || "deepseek-flash";
  return {
    chinese,
    setChinese,
    configuration,
    toggle: () => setChinese((value) => !value),
    running,
    completed,
    issue: issue || (chinese && configuration?.configured === false ? configuration.message : ""),
    failures,
    model,
    ready: items.filter((item) => translationReady(item, model)).length,
    retry: () => {
      failedVersions.current.clear();
      setRetry((value) => value + 1);
    },
    configurationChanged: async () => {
      const result = await api<TranslationStatus>("/translation/status");
      setConfiguration(result);
      failedVersions.current.clear();
      setRetry(value => value + 1);
    },
  };
}
