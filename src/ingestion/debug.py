class Debug:
    def __init__(self, debug_mode: str, sector_name: str):
        self.debug_mode = debug_mode.lower()
        self.sector_name = sector_name.upper()

    def debug(self, message: str):
        """Prints the message with the sector prefix if the debug mode matches."""
        if self.debug_mode in ["all", "true", self.sector_name.lower()]:
            print(f"[{self.sector_name}] {message}")