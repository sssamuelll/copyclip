import json
import sys
import time
import os
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class LLMMetrics:
    timestamp: str
    provider: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    error: Optional[str] = None
    estimated: bool = True

class MetricsCollector:
    def __init__(self, log_file: str = "copyclip_metrics.jsonl"):
        self.log_file = log_file
        self.session_start = time.time()
        self.metrics = []

    def log_llm_call(self, provider: str, model: str, operation: str,
                     input_text: str = "", output_text: str = "", latency_ms: int = 0,
                     cache_hit: bool = False, error: Optional[str] = None,
                     input_tokens: Optional[int] = None,
                     output_tokens: Optional[int] = None):
        """Register metrics for one LLM call.

        If real token counts are supplied they are used and the row is marked
        estimated=False. Otherwise tokens are approximated from word counts and
        the row is flagged estimated=True so a fictional number is never read
        as truth.
        """
        if input_tokens is None or output_tokens is None:
            in_tok = len(input_text.split()) * 1.3
            out_tok = len(output_text.split()) * 1.3 if output_text else 0
            estimated = True
        else:
            in_tok, out_tok = float(input_tokens), float(output_tokens)
            estimated = False

        cost = self._calculate_cost(provider, model, in_tok, out_tok)

        metric = LLMMetrics(
            timestamp=datetime.now().isoformat(),
            provider=provider, model=model, operation=operation,
            input_tokens=int(in_tok), output_tokens=int(out_tok),
            total_tokens=int(in_tok + out_tok),
            cost_usd=cost, latency_ms=latency_ms,
            cache_hit=cache_hit, error=error, estimated=estimated,
        )
        self.metrics.append(metric)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(asdict(metric)) + '\n')
        if os.getenv("COPYCLIP_DEBUG"):
            print(f"[METRICS] {provider}/{model}: {operation} - "
                  f"{metric.total_tokens} tokens, ${cost:.4f}, "
                  f"{latency_ms}ms {'(CACHED)' if cache_hit else ''}"
                  f"{' (est)' if estimated else ''}",
                  file=sys.stderr)

    def _calculate_cost(self, provider: str, model: str,
                       input_tokens: float, output_tokens: float) -> float:
        """Cost in USD. Prices are per MILLION tokens. An unknown model warns
        (rather than silently costing 0) so a missing entry is visible."""
        pricing = {
            'deepseek': {
                'deepseek-chat': {'input': 0.27, 'output': 1.10},
                'deepseek-reasoner': {'input': 0.55, 'output': 2.19},
            },
            'openai': {
                'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
                'gpt-4o': {'input': 2.50, 'output': 10.00},
            },
            'anthropic': {
                'claude-3-5-sonnet': {'input': 3.00, 'output': 15.00},
                'claude-sonnet-4-5': {'input': 3.00, 'output': 15.00},
                'claude-haiku-4-5': {'input': 1.00, 'output': 5.00},
            },
        }
        provider_pricing = pricing.get(provider.lower(), {})
        model_pricing = provider_pricing.get(model)
        if model_pricing is None:
            print(f"[METRICS] warning: unknown model {provider}/{model} — "
                  f"cost recorded as 0; add it to the price table.", file=sys.stderr)
            model_pricing = {'input': 0, 'output': 0}
        input_cost = (input_tokens / 1_000_000) * model_pricing.get('input', 0)
        output_cost = (output_tokens / 1_000_000) * model_pricing.get('output', 0)
        return input_cost + output_cost

    def print_summary(self):
        """Imprime resumen de la sesión."""
        if not self.metrics:
            return

        total_tokens = sum(m.total_tokens for m in self.metrics)
        total_cost = sum(m.cost_usd for m in self.metrics)
        total_time = sum(m.latency_ms for m in self.metrics) / 1000
        cache_hits = sum(1 for m in self.metrics if m.cache_hit)

        print("\n" + "="*60, file=sys.stderr)
        print("📊 SESSION METRICS SUMMARY", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print(f"Total API calls: {len(self.metrics)}", file=sys.stderr)
        print(f"Cache hits: {cache_hits} ({cache_hits/len(self.metrics)*100:.1f}%)",
              file=sys.stderr)
        print(f"Total tokens: {total_tokens:,}", file=sys.stderr)
        print(f"Total cost: ${total_cost:.3f}", file=sys.stderr)
        print(f"Total API time: {total_time:.1f}s", file=sys.stderr)
        print(f"Avg latency: {sum(m.latency_ms for m in self.metrics)/len(self.metrics):.0f}ms",
              file=sys.stderr)

        # Breakdown por proveedor
        by_provider = {}
        for m in self.metrics:
            if m.provider not in by_provider:
                by_provider[m.provider] = {'calls': 0, 'tokens': 0, 'cost': 0}
            by_provider[m.provider]['calls'] += 1
            by_provider[m.provider]['tokens'] += m.total_tokens
            by_provider[m.provider]['cost'] += m.cost_usd

        print("\nBy Provider:", file=sys.stderr)
        for provider, stats in by_provider.items():
            print(f"  {provider}: {stats['calls']} calls, "
                  f"{stats['tokens']:,} tokens, ${stats['cost']:.3f}",
                  file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)

    def reset_run(self):
        """Start a fresh per-run window (the bench scopes metrics to one run)."""
        self._run_start_index = len(self.metrics)

    def run_rollup(self) -> dict:
        """Aggregate the calls logged since the last reset_run() (or all calls
        if reset_run was never called). Used by the bench scorecard."""
        start = getattr(self, "_run_start_index", 0)
        rows = self.metrics[start:]
        out = {
            "calls": len(rows),
            "total_tokens": sum(m.total_tokens for m in rows),
            "total_cost": sum(m.cost_usd for m in rows),
            "estimated": any(m.estimated for m in rows),
            "by_model": {},
            "by_operation": {},
        }
        for m in rows:
            bm = out["by_model"].setdefault(m.model, {"calls": 0, "tokens": 0, "cost": 0.0})
            bm["calls"] += 1; bm["tokens"] += m.total_tokens; bm["cost"] += m.cost_usd
            bo = out["by_operation"].setdefault(m.operation, {"calls": 0, "tokens": 0, "cost": 0.0})
            bo["calls"] += 1; bo["tokens"] += m.total_tokens; bo["cost"] += m.cost_usd
        return out

# Instancia global
metrics_collector = MetricsCollector()
