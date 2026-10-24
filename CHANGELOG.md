# Changelog

## [0.2.0](https://github.com/fran2889/git-ferret/compare/v0.1.0...v0.2.0) (2026-10-24)


### Features

* add config loading, identity resolution, and whitelist globbing ([eb0ec3e](https://github.com/fran2889/git-ferret/commit/eb0ec3e2ab96985d3254ddbd86658b0748d26632))
* add fetch, base ref resolution, and branch listing ([a8aef6f](https://github.com/fran2889/git-ferret/commit/a8aef6f142db45babcf540b1967bd9ba6090829e))
* add local branch and worktree analysis ([d438e53](https://github.com/fran2889/git-ferret/commit/d438e53f2cdac8092e02f689ad69800f42d42ae4))
* add markdown report and CLI entry point ([62ab2c5](https://github.com/fran2889/git-ferret/commit/62ab2c5427eedf88708c2f8519d590e279ac1b25))
* add packaging and git subprocess seam ([5f12296](https://github.com/fran2889/git-ferret/commit/5f1229697327bde1785e9664f854ddd76cd6544d))
* add remote branch filtering and safe-to-delete gating ([6e31fb5](https://github.com/fran2889/git-ferret/commit/6e31fb56b4da4d2f3dabeb445f11a9a44965996f))
* add repository and worktree discovery ([7c69c8a](https://github.com/fran2889/git-ferret/commit/7c69c8adb5bb3a9bd61e77212e9596c59c310bf7))
* add shared finding and report models ([6668ed0](https://github.com/fran2889/git-ferret/commit/6668ed0008cd9076b4f353f9e3bc85cfbacd929f))
* add tree-based merge verdict analysis ([66a88ce](https://github.com/fran2889/git-ferret/commit/66a88ce71548c91b1c4071a57706e54376a0acfb))
* **cli:** add --version and adopt project setup conventions ([#11](https://github.com/fran2889/git-ferret/issues/11)) ([c1eb380](https://github.com/fran2889/git-ferret/commit/c1eb3803a2f9335d6df3ca1d26d10909629de64c))
* report deletion verdicts with one emoji per status ([152cb2c](https://github.com/fran2889/git-ferret/commit/152cb2cbf0f38946153336298d67fda199db9184))


### Bug Fixes

* **cli:** give bad config and failed runs their documented exit codes ([#42](https://github.com/fran2889/git-ferret/issues/42)) ([21b14b7](https://github.com/fran2889/git-ferret/commit/21b14b7b08b9b4f9e216bc6ee1aa74ac074a123b))
* **cli:** make usage errors one line and make publishing retryable ([#2](https://github.com/fran2889/git-ferret/issues/2)) ([63cb432](https://github.com/fran2889/git-ferret/commit/63cb43209c63b56dc46a1b27c67605b4cefab286))
* **cli:** stop the run when git cannot be executed ([#41](https://github.com/fran2889/git-ferret/issues/41)) ([5ac22aa](https://github.com/fran2889/git-ferret/commit/5ac22aa7bd78dcecd4b7b1f85b41d42f2553b26b))
* **cli:** write the report as UTF-8 regardless of console locale ([#40](https://github.com/fran2889/git-ferret/issues/40)) ([bdd26ed](https://github.com/fran2889/git-ferret/commit/bdd26ed419bebcbcd70aac91bd15a223f0427d87))
* report a linked worktree once, under its main repository ([c94ee88](https://github.com/fran2889/git-ferret/commit/c94ee88a9dc1e15bdd74a0e81789f6a546208ac4))
* report a missing remote in `remote` and `merged` too ([15d0fbc](https://github.com/fran2889/git-ferret/commit/15d0fbc14db5e162a84b9f376507ae74f150b96b))
* report fresh clones accurately and usage errors as exit 1 ([4bdc27d](https://github.com/fran2889/git-ferret/commit/4bdc27ddaa122103fefb25626aacb3348a3d77b8))
* resolve base ref after fetching and mark unfetched state stale ([7ea46f2](https://github.com/fran2889/git-ferret/commit/7ea46f2c8873a9f7c83bee945d22abec31ed3e7d))
* state the real stale count in the warning, over the whole run ([ed8aa16](https://github.com/fran2889/git-ferret/commit/ed8aa16b4e9fc64c910c2b3268f838b2b87977fc))
* stop calling a repository with commits "no commits yet" ([486d9cc](https://github.com/fran2889/git-ferret/commit/486d9cc05a1a8a078c9a9d51d2847007c3db769b))
* stop claiming `local` skipped a branch analysis it still runs ([4ad3a24](https://github.com/fran2889/git-ferret/commit/4ad3a24e8b3c285148dfe701ad1aeb73f6495dcb))
* surface fetch failures instead of discarding them in the CLI ([793de32](https://github.com/fran2889/git-ferret/commit/793de329a72df8b73dc442dddbc39fd8be03b814))
* treat a no-upstream local branch as unpushed in the deletion gate ([ef6cd36](https://github.com/fran2889/git-ferret/commit/ef6cd3633058a381c319417231ddb5a8caa3e80b))


### Documentation

* add AGENTS.md for AI agents ([#31](https://github.com/fran2889/git-ferret/issues/31)) ([978a5f0](https://github.com/fran2889/git-ferret/commit/978a5f0f8c2cb8b34032cd1611c85589211b2418))
* add git-wombat design document ([57110ab](https://github.com/fran2889/git-ferret/commit/57110ab1fc68421b557592c0024a3563e50c67d8))
* add git-wombat implementation plan ([e40bf62](https://github.com/fran2889/git-ferret/commit/e40bf62e60837194da75080bb4d60a1599019f4c))
* add user-facing README ([a5406c4](https://github.com/fran2889/git-ferret/commit/a5406c42bd50d16cc6d200c3b416fc8780fe4c91))
* consolidate the contributor guides ([#30](https://github.com/fran2889/git-ferret/issues/30)) ([ce567eb](https://github.com/fran2889/git-ferret/commit/ce567eb9da93ce365eb1e6d92bb3ea868f6583aa))
* cover running the checkout with uv and uvx ([817a534](https://github.com/fran2889/git-ferret/commit/817a5347de031f450427b4016ccf3f20c4997c3f))
* declare GPL-3.0-only licence ([8ec8168](https://github.com/fran2889/git-ferret/commit/8ec81688125ea12bcf88fa56b449b57b75d6196b))
* describe deletion verdicts and the streamed report layout ([aad87a5](https://github.com/fran2889/git-ferret/commit/aad87a5c2717c733f23ead118be1675ef0e3599b))
* document the development workflow and add badges ([6e4b280](https://github.com/fran2889/git-ferret/commit/6e4b280435bd24bd4b59bf92915806a0b84333d3))
* document venv setup from scratch and recovering a broken one ([46e40d8](https://github.com/fran2889/git-ferret/commit/46e40d8d702babed22f2bf5891b6b4adaa844059))
* tidy module docstrings ([ce3982e](https://github.com/fran2889/git-ferret/commit/ce3982e7b8606314c0393c4844c14624dba0b750))
