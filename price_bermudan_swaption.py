from portfolio import default_portfolio_state, price_portfolio


def main() -> None:
    priced_portfolio = price_portfolio(default_portfolio_state())
    bermudan_row = priced_portfolio.loc[
        priced_portfolio["TradeKey"] == "bermudan_swaption"
    ].iloc[0]
    print("Bermudan Swaption Example")
    print(f"Structure: {bermudan_row['Structure']}")
    print(f"NPV: {bermudan_row['NPV']:.2f}")


if __name__ == "__main__":
    main()
