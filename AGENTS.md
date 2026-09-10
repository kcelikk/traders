# Repository Guidelines

## Ajan Rolü ve Çalışma Sınırı

Ajanın rolü; proje kodunu denetlemek, hata, sorun ve eksikleri tespit etmek, geliştirme önerileri sunmak ve strateji geliştirmektir. Yalnızca incele, analiz et ve Türkçe raporla; önerileri uygulama.

Kod, test, yapılandırma, dokümantasyon veya veri dosyalarını oluşturma, değiştirme ya da silme. Kurulum, otomatik düzeltme, commit, dağıtım veya çalışan sistemin durumunu değiştiren işlemler yapma. İncelemelerde salt okunur araç ve komutlar kullan. Bu belgedeki geliştirme, test ve PR yönergeleri referans niteliğindedir; ajana değişiklik yapma yetkisi vermez.

Bulguları önem derecesi, ilgili dosya/satır, kanıt, olası etki ve çözüm önerisiyle raporla. Doğrulanmış hataları varsayımlardan ayır; doğrulanamayan noktaları ve inceleme eksiklerini açıkça belirt. Strateji önerilerinde gerekçe, risk ve doğrulama yöntemini açıkla; ölçüm olmadan kârlılık veya performans iddiasında bulunma.

## Project Structure & Module Organization

`fbot/` implements an event-driven Binance USDⓈ-M Futures trading system. Keep deterministic business logic in `fbot/core/`, network and filesystem integration in `fbot/gateway/`, recording in `fbot/recorder/`, and execution adapters in `fbot/execution/`. Replay and research utilities live in their respective subpackages; `fbot/api/` serves console data, and `ui/` holds HTML/JavaScript assets.

Use `scripts/` for command-line workflows, `config/` for TOML configuration, and `tests/fixtures/` for small reproducible datasets. Runtime recordings and research output belong in ignored `data/`. Read `CLAUDE.md`, `docs/PHASE.md`, and recent `docs/decisions/` entries before changing behavior; phase status comes from `docs/PHASE.md`.

## Build, Test, and Development Commands

- `make setup`: create `.venv` and install pinned development dependencies.
- `make test`: run the complete pytest suite.
- `make test-determinism`: check replay reproducibility and core purity.
- `.venv/bin/pytest -q tests/test_risk.py`: run a focused test module.
- `make run-recorder REC=dev-check DURATION=60`: record public market data locally for 60 seconds.
- `make verify-recording REC=dev-check`: validate recording integrity.
- `make replay REC=dev-check MAXF=1`: replay one recorded file.
- `make docker-build`: build the recorder container.

## Coding Style & Naming Conventions

Use four-space Python indentation, type annotations, `snake_case` functions/modules, and `PascalCase` classes. Follow adjacent code; no formatter or linter is configured. Use `Decimal` for financial arithmetic and configuration for thresholds. Keep core modules free of network, database, filesystem, and logging dependencies. Inject time and seed randomness so identical recordings produce bit-identical decisions. Existing documentation and comments predominantly use Turkish.

## Testing Guidelines

Use pytest with `tests/test_<module>.py` files and descriptive `test_<behavior>` functions. Cover changed behavior, rejection paths, and boundary conditions using deterministic fixtures. Run the full suite before submitting; determinism failures block merging. No numerical coverage threshold is configured.

## Commit & Pull Request Guidelines

History uses concise Turkish summaries, often prefixed with `Faz N:`, `ADR NNNN:`, `fix:`, or `perf:`. Follow the relevant pattern. PRs should describe the behavior change, link applicable issues or ADRs, report validation commands/results, and include screenshots for UI changes. Record architectural decisions as `docs/decisions/NNNN-baslik.md`.

## Security & Scope

Keep secrets out of source, logs, and images; use `.env.example` for placeholders. Paper mode is the default. Follow the approval requirements in `CLAUDE.md` for live execution, dependencies, destructive operations, and phase changes.
