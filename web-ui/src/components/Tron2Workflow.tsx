import { useEffect, useState } from 'react';

type Camera = 'overview' | 'before' | 'after';
type Task = 'cube_lift' | 'pick_place';
type Feedback = 'oracle' | 'single' | 'text' | 'vdm';

interface Evaluation {
  state: 'running' | 'complete' | 'stopped' | 'error';
  completed: number;
  total: number;
  successes: number;
  task: Task;
  stage: Feedback | 'baseline';
  baseline_successes: number | null;
  visual_directions: number | null;
  error: string | null;
  latest: {
    seed: number;
    failure: string | null;
    lift_cm: number | null;
    pose_requests: number;
    code: string;
    frames: Record<Camera, string>;
  } | null;
}

interface Status {
  perception: boolean;
  owned_perception: boolean;
  run: Evaluation | null;
}

const cameraLabels: Record<Camera, string> = {
  overview: '试验结束 · 全景',
  before: '首轮前 · 头部相机',
  after: '首轮后 · 头部相机',
};

const runLabels = {
  running: '运行中',
  complete: '已完成',
  stopped: '已停止',
  error: '运行失败',
};

const taskLabels: Record<Task, string> = { cube_lift: 'Cube Lift', pick_place: 'Pick & Place' };
const stageLabels: Record<Evaluation['stage'], string> = {
  oracle: 'Oracle',
  single: '单轮',
  text: '多轮文本',
  baseline: '配对文本基线',
  vdm: '文本 + VDM',
};

const secondary = 'rounded-md border border-surface-border-light px-3 py-2 text-sm text-text-primary hover:bg-surface-overlay disabled:opacity-45';
const primary = 'rounded-md bg-accent px-4 py-2 text-sm font-semibold text-black hover:bg-accent-light disabled:opacity-40';
const field = 'mt-1.5 w-full rounded-md border border-surface-border-light bg-surface-sunken px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none';

async function fetchJson<T>(path: string, data?: object): Promise<T> {
  const response = await fetch(`/api/tron2${path}`, data === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok) {
    throw new Error(typeof value.detail === 'string' ? value.detail : '请求失败，请核对输入。');
  }
  return value as T;
}

export function Tron2Workflow() {
  const [status, setStatus] = useState<Status>();
  const [url, setUrl] = useState('http://127.0.0.1:18086/v1/chat/completions');
  const [model, setModel] = useState('Qwen/Qwen2.5-Coder-3B-Instruct');
  const [seed, setSeed] = useState('41');
  const [trials, setTrials] = useState('1');
  const [task, setTask] = useState<Task>('cube_lift');
  const [feedback, setFeedback] = useState<Feedback>('text');
  const [occlusion, setOcclusion] = useState(true);
  const [camera, setCamera] = useState<Camera>('overview');
  const [pending, setPending] = useState('');
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const update = await fetchJson<Status>('/status');
        if (mounted) setStatus(update);
      } catch {
        if (mounted) setStatus(undefined);
      } finally {
        if (mounted) timer = setTimeout(poll, 1200);
      }
    }
    poll();
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, []);

  async function update(name: string, fn: () => Promise<void>) {
    setPending(name);
    setError('');
    try {
      await fn();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '请求失败。');
    } finally {
      setPending('');
    }
  }

  function changeEndpoint(change: (value: string) => void, value: string) {
    change(value);
    setConnected(false);
  }

  function changeProcess(path: string) {
    return update(path, async () => setStatus(await fetchJson<Status>(path, {})));
  }

  const run = status?.run;
  const running = run?.state === 'running';
  const latest = run?.latest;
  const options = { model: model.trim(), server_url: url.trim() };
  const settingsReady = Boolean(options.model && options.server_url);

  return (
    <div className="h-full overflow-y-auto bg-surface text-text-primary">
      <header className="border-b border-surface-border bg-surface-raised">
        <nav className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <a href="/" className="flex items-center gap-3 font-display font-semibold text-text-primary">
            <img src="/capx_logo.svg" className="h-7 w-7" alt="" />
            CaP-X
          </a>
          <span className="text-sm text-text-secondary">TRON2 · MuJoCo</span>
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-5 pb-12 pt-8 sm:px-8 lg:pt-12">
        <h1 className="font-display text-3xl font-bold tracking-tight sm:text-4xl">TRON2 {taskLabels[task]}</h1>
        <p className="mt-2 text-sm text-text-secondary">桌面世界 Z 0.620 m · 安装高差 0.450 m</p>
        <div className="mt-8 grid items-start gap-7 lg:grid-cols-[minmax(290px,340px)_1fr]">
          <div className="divide-y divide-surface-border rounded-lg border border-surface-border bg-surface-raised">
            <section className="space-y-3 p-5" aria-labelledby="perception-heading">
              <div className="flex items-center justify-between gap-2">
                <h2 id="perception-heading" className="font-semibold">1. 感知服务器</h2>
                <span role="status" className={`text-xs ${status?.perception ? 'text-nv-green' : 'text-text-secondary'}`}>
                  {status ? status.perception ? '已就绪' : '未启动' : '连接界面中'}
                </span>
              </div>
              <p className="text-sm text-text-secondary">TRON2 RGB-D 位姿服务 · 8121</p>
              {status?.owned_perception ? (
                <button className={secondary} disabled={Boolean(pending) || running} onClick={() => changeProcess('/perception/stop')}>
                  停止感知服务器
                </button>
              ) : (
                <button className={secondary} disabled={!status || status.perception || Boolean(pending)}
                  onClick={() => changeProcess('/perception/start')}>
                  {pending === '/perception/start' ? '启动中' : '启动感知服务器'}
                </button>
              )}
            </section>

            <section className="space-y-3 p-5" aria-labelledby="model-heading">
              <h2 id="model-heading" className="font-semibold">2. 设置 LLM 代理</h2>
              <label className="block text-sm text-text-secondary">
                Chat Completions 地址
                <input type="url" className={field} value={url} disabled={running || Boolean(pending)}
                  onChange={(event) => changeEndpoint(setUrl, event.target.value)} />
              </label>
              <label className="block text-sm text-text-secondary">
                模型 ID
                <input className={field} value={model} disabled={running || Boolean(pending)}
                  onChange={(event) => changeEndpoint(setModel, event.target.value)} />
              </label>
              <div className="flex flex-wrap items-center gap-3">
                <button className={secondary} disabled={!settingsReady || running || Boolean(pending)}
                  onClick={() => update('model', async () => {
                    setConnected(false);
                    await fetchJson('/model/check', options);
                    setConnected(true);
                  })}>
                  {pending === 'model' ? '正在测试' : '测试 LLM 连接'}
                </button>
                {connected && <span role="status" className="text-xs text-nv-green">模型已响应</span>}
              </div>
            </section>

            <section className="space-y-3 p-5" aria-labelledby="evaluation-heading">
              <h2 id="evaluation-heading" className="font-semibold">3. 运行评估</h2>
              <div>
                <label htmlFor="tron2-task" className="block text-sm text-text-secondary">任务</label>
                <select id="tron2-task" className={field} value={task} disabled={running || Boolean(pending)}
                  onChange={(event) => setTask(event.target.value as Task)}>
                  <option value="cube_lift">Cube Lift</option>
                  <option value="pick_place">Pick &amp; Place</option>
                </select>
              </div>
              <div>
                <label htmlFor="tron2-feedback" className="block text-sm text-text-secondary">反馈方式</label>
                <select id="tron2-feedback" className={field} value={feedback} disabled={running || Boolean(pending)}
                  onChange={(event) => setFeedback(event.target.value as Feedback)}>
                  <option value="single">单轮</option>
                  <option value="text">多轮文本</option>
                  <option value="vdm">多轮文本与 VDM 配对</option>
                  <option value="oracle">Oracle</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm text-text-secondary">
                <input type="checkbox" checked={occlusion} disabled={running || Boolean(pending)}
                  onChange={(event) => setOcclusion(event.target.checked)} /> 头部相机部分遮挡
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-sm text-text-secondary">
                  起始种子
                  <input className={field} type="number" min="1" value={seed}
                    disabled={running || Boolean(pending)} onChange={(event) => setSeed(event.target.value)} />
                </label>
                <label className="text-sm text-text-secondary">
                  试验数
                  <input className={field} type="number" min="1" value={trials}
                    disabled={running || Boolean(pending)} onChange={(event) => setTrials(event.target.value)} />
                </label>
              </div>
              {running ? (
                <button className={secondary} disabled={Boolean(pending)}
                  onClick={() => changeProcess('/evaluation/stop')}>停止评估</button>
              ) : (
                <button className={primary} disabled={!status?.perception || (!settingsReady && feedback !== 'oracle') || Boolean(pending) || !seed || !trials}
                  onClick={() => update('evaluation', async () => {
                    setCamera('overview');
                    setStatus(await fetchJson<Status>('/evaluation/start', {
                      ...options, task, feedback, occlusion, start_seed: Number(seed), trials: Number(trials),
                    }));
                  })}>运行评估</button>
              )}
            </section>
            {error && <p role="alert" className="break-words px-5 py-4 text-sm text-red-300">{error}</p>}
          </div>

          <section className="min-w-0 overflow-hidden rounded-lg border border-surface-border bg-surface-raised" aria-labelledby="view-heading">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border px-5 py-4">
              <h2 id="view-heading" className="font-semibold">MuJoCo 评估画面</h2>
              {run && <span role="status" className="text-sm text-text-secondary">
                {taskLabels[run.task]} · {stageLabels[run.stage]} · {runLabels[run.state]} · {run.completed}/{run.total} 已运行 · {run.successes} 成功
              </span>}
            </div>
            <div className="relative flex aspect-[4/3] max-h-[540px] items-center justify-center bg-surface-sunken">
              {latest ? (
                <img src={latest.frames[camera]} alt={cameraLabels[camera]} className="absolute inset-0 h-full w-full object-contain" />
              ) : (
                <p className="px-4 text-center text-sm text-text-secondary">
                  {running ? '正在生成并执行程序，首个试验结束后显示画面。' : '运行评估后在这里查看仿真画面。'}
                </p>
              )}
            </div>
            {latest && (
              <div className="space-y-4 p-5">
                {run && run.baseline_successes !== null && (
                  <p className="text-sm text-text-secondary">
                    文本基线 {run.baseline_successes}/{run.total}
                    {run.visual_directions !== null && ` · VDM 方向判对 ${run.visual_directions} 次`}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  {(Object.keys(cameraLabels) as Camera[]).map((name) => (
                    <button key={name} className={`${secondary} ${camera === name ? 'border-accent text-accent' : ''}`}
                      aria-pressed={camera === name} onClick={() => setCamera(name)}>{cameraLabels[name]}</button>
                  ))}
                </div>
                <p className="text-sm text-text-secondary">
                  种子 {latest.seed} · 感知调用 {latest.pose_requests}
                  {latest.failure && ` · 首轮 ${latest.failure}`}
                  {latest.lift_cm !== null && ` · 抬升 ${latest.lift_cm.toFixed(2)} cm`}
                </p>
                <details>
                  <summary className="cursor-pointer text-sm text-text-primary">查看 LLM 生成的程序</summary>
                  <pre className="mt-3 overflow-x-auto rounded-md bg-surface-sunken p-4 text-xs leading-6 text-text-primary">
                    <code>{latest.code}</code>
                  </pre>
                </details>
              </div>
            )}
            {run?.error && <p role="alert" className="break-words p-5 text-sm text-red-300">{run.error}</p>}
          </section>
        </div>
      </main>
    </div>
  );
}
