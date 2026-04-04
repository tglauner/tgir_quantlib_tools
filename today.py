import QuantLib as ql


def main() -> None:
    today = ql.Date().todaysDate()
    ql.Settings.instance().evaluationDate = today
    print("Today's Date in QuantLib:", today)


if __name__ == "__main__":
    main()
