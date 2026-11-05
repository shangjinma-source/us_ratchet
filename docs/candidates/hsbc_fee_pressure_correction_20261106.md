# Commission sensitivity correction

Earlier report incorrectly treated the first threshold-crossing order as uncertain. Superseded: the existing verified core and research_contracts/hsbc_trade25_20261024.json explicitly waive that first crossing. Only exact pre-trade250000HKD retains wording uncertainty. The former crossing-charge upper number is withdrawn as official fee; at most it was a nonofficial stress assumption and is no longer reported.

The script now delegates every quote to core.hsbc_trade25_commission.quote_commission. Monthly accumulation is Hong Kong local calendar month, not US trading-date month. Daily intraday fills lack exact time; run earliest/open and latest/close timestamp scenarios, which are neither exact bills nor guaranteed extrema. Known OPEN fills remain9:30NewYork with DST conversion.7.8 is a scenario FX, not a broker rate. Charging-unit and other-fee limits remain explicit.

Both partial-book output files were regenerated. Four tests passed: first crossing waived, exact prethreshold ambiguity,1000/1001share fee schedule, and HongKong month rollover intraday uncertainty. No strategy net return/full cost replay or production modification was performed. RSI late-window rejection is independent; no extra cost replay is planned.
