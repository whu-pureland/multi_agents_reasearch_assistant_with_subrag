<template>
  <div v-if="!job" class="text-sm text-slate-600">加载中...</div>
  <div v-else class="space-y-4">
    <section class="rounded-lg border bg-white p-5 shadow-sm">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-base font-semibold">任务详情</h2>
          <p class="mt-2 text-sm text-slate-700">{{ job.query }}</p>
        </div>
        <span
          class="inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold text-white"
          :style="{ background: statusColor(job.status) }"
        >
          {{ job.status }}
        </span>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button
          class="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          :disabled="busy || job.status === 'running'"
          @click="onStart"
        >
          {{ job.status === "running" ? "运行中..." : "开始研究" }}
        </button>

        <label class="flex items-center gap-2 text-sm text-slate-700">
          <span class="font-medium">上传私有资料</span>
          <input
            type="file"
            class="text-sm"
            :disabled="busy"
            @change="(e) => onFileChange(e)"
          />
        </label>

        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      </div>
    </section>

    <section class="rounded-lg border bg-white p-5 shadow-sm">
      <h3 class="text-sm font-semibold">TODO 列表</h3>
      <ol class="mt-3 list-decimal space-y-3 pl-5">
        <li v-for="t in job.todos" :key="t.id" class="text-sm">
          <div class="flex items-center gap-2">
            <span
              class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold text-white"
              :style="{ background: statusColor(t.status) }"
            >
              {{ t.status }}
            </span>
            <span class="font-semibold text-slate-900">{{ t.title }}</span>
          </div>

          <div v-if="notesByTodo.get(t.id)" class="mt-2 rounded-md border bg-slate-50 p-3">
            <div class="prose prose-slate max-w-none text-sm" v-html="renderMarkdown(notesByTodo.get(t.id)!)" />
          </div>
        </li>
      </ol>
    </section>

    <section class="rounded-lg border bg-white p-5 shadow-sm">
      <h3 class="text-sm font-semibold">报告</h3>
      <div v-if="job.report" class="mt-3 rounded-md border bg-slate-50 p-3">
        <div class="prose prose-slate max-w-none text-sm" v-html="renderMarkdown(job.report)" />
      </div>
      <p v-else class="mt-2 text-sm text-slate-600">尚未生成报告（任务结束后自动生成）。</p>
    </section>

    <section class="rounded-lg border bg-white p-5 shadow-sm">
      <h3 class="text-sm font-semibold">上传资料</h3>
      <ul v-if="job.uploads.length" class="mt-3 space-y-1 text-sm">
        <li v-for="u in job.uploads" :key="u.stored_path" class="font-mono text-xs text-slate-700">
          {{ u.ingested ? "✓" : "…" }} {{ u.filename }}
        </li>
      </ul>
      <p v-else class="mt-2 text-sm text-slate-600">暂无上传文件。</p>
    </section>

    <section class="rounded-lg border bg-white p-5 shadow-sm">
      <h3 class="text-sm font-semibold">来源（Top）</h3>
      <ol v-if="topSources.length" class="mt-3 list-decimal space-y-2 pl-5 text-sm">
        <li v-for="s in topSources" :key="s.id">
          <div class="font-mono text-[11px] text-slate-500">{{ s.id }} ({{ s.quality_score.toFixed(2) }})</div>
          <a v-if="s.url.startsWith('http')" class="text-slate-900 underline" :href="s.url" target="_blank">
            {{ s.title }}
          </a>
          <span v-else class="text-slate-900">{{ s.title }}</span>
        </li>
      </ol>
      <p v-else class="mt-2 text-sm text-slate-600">尚未收集来源（任务运行后自动填充）。</p>
    </section>

    <section class="rounded-lg border bg-white p-5 shadow-sm">
      <h3 class="text-sm font-semibold">事件流（SSE）</h3>
      <ul class="mt-3 space-y-1">
        <li v-for="(ev, idx) in recentEvents" :key="idx" class="font-mono text-xs text-slate-700">
          {{ JSON.stringify(ev) }}
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { Job } from "../api";
import { getJob, startJob, uploadFile } from "../api";
import { renderMarkdown } from "../lib/markdown";

const props = defineProps<{ jobId: string }>();

const job = ref<Job | null>(null);
const busy = ref(false);
const error = ref<string | null>(null);

let es: EventSource | null = null;
let pollTimer: number | null = null;

function statusColor(status: string): string {
  if (status === "done" || status === "succeeded") return "#1b5e20";
  if (status === "in_progress" || status === "running") return "#0d47a1";
  if (status === "failed") return "#b71c1c";
  return "#37474f";
}

const notesByTodo = computed(() => {
  const map = new Map<string, string>();
  for (const n of job.value?.notes ?? []) map.set(n.todo_id, n.content_md);
  return map;
});

const topSources = computed(() =>
  [...(job.value?.sources ?? [])].sort((a, b) => b.quality_score - a.quality_score).slice(0, 20),
);

const recentEvents = computed(() => (job.value?.events ?? []).slice(-18).reverse());

async function refresh() {
  try {
    job.value = await getJob(props.jobId);
  } catch (e) {
    error.value = String(e);
  }
}

async function onStart() {
  busy.value = true;
  error.value = null;
  try {
    job.value = await startJob(props.jobId);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  busy.value = true;
  error.value = null;
  try {
    job.value = await uploadFile(props.jobId, file);
  } catch (err) {
    error.value = String(err);
  } finally {
    busy.value = false;
    input.value = "";
  }
}

function startSse() {
  es = new EventSource(`/api/jobs/${props.jobId}/events/stream`);
  es.onmessage = () => {
    void refresh();
  };
  es.onerror = () => {
    es?.close();
    es = null;
  };
}

onMounted(() => {
  void refresh();
  startSse();
  pollTimer = window.setInterval(() => void refresh(), 2500);
});

onBeforeUnmount(() => {
  if (pollTimer) window.clearInterval(pollTimer);
  es?.close();
  es = null;
});
</script>

