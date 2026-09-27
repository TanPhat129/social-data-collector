from app.presentation.cli import main


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nĐã dừng an toàn. Lead đã commit vẫn nằm trong PostgreSQL/outbox.")
