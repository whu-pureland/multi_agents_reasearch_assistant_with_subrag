<template>
  <section class="rounded-lg border bg-white p-5 shadow-sm">
    <h2 class="text-base font-semibold">创建研究任务</h2>

    <label class="mt-4 block text-sm font-medium text-slate-700">研究问题</label>
    <textarea
      v-model="query"
      class="mt-2 w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring"
      rows="7"
      placeholder="例如：请对“Multi-Agent 深度研究系统”的关键设计与工程实现做系统梳理..."
    />

    <div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
      <label class="text-sm">
        <div class="font-medium text-slate-700">最大 TODO 数</div>
        <input
          v-model.number="settings.max_todos"
          class="mt-2 w-full rounded-md border px-3 py-2 text-sm"
          type="number"
          min="3"
          max="20"
        />
      </label>

      <label class="text-sm">
        <div class="font-medium text-slate-700">每个 TODO 的网页结果</div>
        <input
          v-model.number="settings.web_results_per_todo"
          class="mt-2 w-full rounded-md border px-3 py-2 text-sm"
          type="number"
          min="0"
          max="20"
        />
      </label>

      <label class="text-sm">
        <div class="font-medium text-slate-700">私有语义检索 TopK</div>
        <input
          v-model.number="settings.private_semantic_top_k"
          class="mt-2 w-full rounded-md border px-3 py-2 text-sm"
          type="number"
          min="0"
          max="20"
        />
      </label>
    </div>

    <div class="mt-4 flex flex-wrap gap-4 text-sm text-slate-700">
      <label class="flex items-center gap-2">
        <input v-model="settings.include_private_knowledge" type="checkbox" class="h-4 w-4" />
        <span class="font-medium">私有知识对齐</span>
      </label>

      <label class="flex items-center gap-2">
        <input v-model="settings.enable_fact_check" type="checkbox" class="h-4 w-4" />
        <span class="font-medium">报告事实核查</span>
      </label>

      <label class="flex items-center gap-2">
        <input v-model="settings.enable_mcp_tools" type="checkbox" class="h-4 w-4" />
        <span class="font-medium">启用 MCP 工具</span>
      </label>
    </div>

    <p class="mt-2 text-xs text-slate-500">
      私有语义检索与事实核查需要配置后端 OpenAI Key（见根目录 <code>.env</code>）。
    </p>

    <div class="mt-5 flex items-center gap-3">
      <button
        class="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        :disabled="busy || query.trim().length < 3"
        @click="onCreate"
      >
        {{ busy ? "创建中..." : "创建任务" }}
      </button>
      <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import type { JobSettings } from "../api";
import { createJob } from "../api";

const router = useRouter();
const query = ref("");
const busy = ref(false);
const error = ref<string | null>(null);

const settings = reactive<JobSettings>({
  max_todos: 8,
  web_results_per_todo: 5,
  include_private_knowledge: true,
  private_semantic_top_k: 5,
  enable_fact_check: true,
  enable_mcp_tools: false,
});

async function onCreate() {
  busy.value = true;
  error.value = null;
  try {
    const job = await createJob(query.value, settings);
    await router.push(`/jobs/${job.id}`);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}
</script>
