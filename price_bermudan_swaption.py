from portfolio import default_portfolio_state, price_portfolio


def main() -> None:
    priced_portfolio = price_portfolio(default_portfolio_state())
    for trade_key in ("bermudan_swaption", "bermudan_swaption_2"):
        bermudan_row = priced_portfolio.loc[
            priced_portfolio["TradeKey"] == trade_key
        ].iloc[0]
        print(bermudan_row["Type"])
        print(f"Structure: {bermudan_row['Structure']}")
        print(f"NPV: {bermudan_row['NPV']:.2f}")
        print("")


if __name__ == "__main__":
    main()
