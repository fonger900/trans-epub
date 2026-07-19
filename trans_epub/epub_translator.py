def _print_results(
    output_path: str,
    engine: str,
    total_chars: int,
    cached_chars: int,
    failed: list[tuple[str, str]],
) -> None:
    """Print final summary, cost, and failure details."""
    if engine == "gemini":
        from .engines.gemini import actual_gemini_cost, get_gemini_usage, get_gemini_stats

        cost = actual_gemini_cost()
        prompt_tok, output_tok = get_gemini_usage()
        stats = get_gemini_stats()
        
        if cost > 0:
            console.print(
                f"[bold]Cost:[/bold] ${cost:.4f}  "
                f"([dim]{prompt_tok:,} in + {output_tok:,} out = "
                f"{prompt_tok + output_tok:,} tokens[/dim])"
            )
        elif prompt_tok + output_tok > 0:
            console.print(
                f"[bold]Cost:[/bold] [green]free[/green]  "
                f"([dim]{prompt_tok:,} in + {output_tok:,} out = "
                f"{prompt_tok + output_tok:,} tokens[/dim])"
            )
        
        # Print detailed token statistics for future estimation
        if stats["total_tokens"] > 0:
            console.print(
                f"\n[dim]Token analysis (use for future estimates):[/dim]"
            )
            console.print(
                f"  Total tokens: {stats['total_tokens']:,} "
                f"({stats['prompt_fraction']*100:.1f}% input, {(1-stats['prompt_fraction'])*100:.1f}% output)"
            )
            console.print(
                f"  API calls: {stats['api_calls']}"
            )
            console.print(
                f"  Input characters: {stats['input_chars']:,}"
            )
            console.print(
                f"  [bold]Tokens per character: {stats['tokens_per_char']:.2f}[/bold] "
                f"[yellow](key metric for future estimates)[/yellow]"
            )
            
            if stats['api_calls'] > 0:
                tokens_per_call = stats['total_tokens'] / stats['api_calls']
                console.print(
                    f"  Average tokens per API call: {tokens_per_call:,.0f}"
                )

    console.print(
        f"[bold green]✓ Done[/bold green] → {output_path}  "
        f"([dim]{total_chars:,} chars translated ({total_chars // 4:,} tokens)[/dim], "
        f"[dim]{cached_chars:,} cached[/dim])"
    )

    if failed:
        # Categorize failures for targeted recovery advice
        quota_fails = []
        network_fails = []
        parse_fails = []
        other_fails = []
        for name, err in failed:
            err_lower = err.lower()
            if any(
                kw in err_lower
                for kw in (
                    "quota",
                    "limit exceeded",
                    "daily limit",
                    "insufficient quota",
                    "billing",
                    "payment required",
                    "rate limit",
                )
            ):
                quota_fails.append((name, err))
            elif any(
                kw in err_lower
                for kw in (
                    "timeout",
                    "connection",
                    "network",
                    "reset by peer",
                    "refused",
                )
            ):
                network_fails.append((name, err))
            elif "parse" in err_lower or "json" in err_lower:
                parse_fails.append((name, err))
            else:
                other_fails.append((name, err))

        console.print(
            f"\n[bold red]{len(failed)} item(s) failed[/bold red]"
            f" ([dim]re-run to retry[/dim]):"
        )

        def _show_group(label, items, advice):
            if not items:
                return
            console.print(f"\n  [bold]{label}[/bold] ({len(items)}):")
            for name, err in items[:5]:
                short = _short_name(name)
                console.print(f"    [red]•[/red] {short}: {err[:120]}")
            if len(items) > 5:
                console.print(f"    [dim]... and {len(items) - 5} more[/dim]")
            console.print(f"  [dim]Fix: {advice}[/dim]")

        _show_group(
            "Quota / rate limit",
            quota_fails,
            "Check API billing, reduce --creativity, wait before retrying.",
        )
        _show_group(
            "Network / timeout",
            network_fails,
            "Check internet connection. Set GEMINI_TIMEOUT higher or reduce --threads.",
        )
        _show_group(
            "Parse / JSON error",
            parse_fails,
            "API returned malformed response. Try different --creativity or engine.",
        )
        _show_group(
            "Other",
            other_fails,
            "Check error details above. Run with --verbose for request-level logs.",
        )
