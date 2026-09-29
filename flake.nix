{
  description = "Development environment for the amazon_challenge repository";

  inputs = {
    # Tracks the rolling release for the latest stable packages
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      # Supports macOS and Linux out of the box
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; });
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          default = pkgs.mkShell {
            # pkgs.python3 aliases the latest stable Python version in nixpkgs 
            packages = with pkgs; [
              python3
              python3Packages.pip
              python3Packages.virtualenv
              bun
              nodejs ## fallback for bun, to avoid arcoded nodejs version issues
              git      # Added to expose Git inside the direnv shell
            ];

            shellHook = ''
              echo "Starting Nix dev environment..."
              
              # Isolate Python dependencies locally 
              VENV_DIR=".venv"
              if [ ! -d "$VENV_DIR" ]; then
                echo "Creating new virtual environment in $VENV_DIR..."
                python -m venv $VENV_DIR
              fi
              
              source $VENV_DIR/bin/activate
              
              # Automatically install the amazon_challenge project requirements
              if [ -f "requirements.txt" ]; then
                pip install -r requirements.txt
              fi
              
              if [ -f "pyproject.toml" ]; then
                pip install -e .
              fi
              
              echo "Ready. Currently using $(python --version)"
            '';
          };
        }
      );
    };
}