{
  description = "Simple Python Communications";

  inputs.nixpkgs.url = github:NixOS/nixpkgs/nixos-25.05;

  outputs = { self, nixpkgs }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };
      sipyco = pkgs.python3Packages.buildPythonPackage {
        pname = "sipyco";
        version = "1.8";
        src = self;
        propagatedBuildInputs = with pkgs.python3Packages; [ pybase64 numpy ];
        checkPhase = "python -m unittest discover sipyco.test";
      };
      sipyco-aarch64 = (with nixpkgs.legacyPackages.aarch64-linux; python3Packages.buildPythonPackage {
        inherit (sipyco) pname version src;
        propagatedBuildInputs = with python3Packages; [ pybase64 numpy ];
      });
      latex-sipyco-manual = pkgs.texlive.combine {
        inherit (pkgs.texlive)
          scheme-basic latexmk cmap collection-fontsrecommended fncychap
          titlesec tabulary varwidth framed fancyvrb float wrapfig parskip
          upquote capt-of needspace etoolbox booktabs xcolor;
      };
    in rec {
      packages.x86_64-linux = {
        inherit sipyco latex-sipyco-manual;
        default = sipyco;
        sipyco-manual-html = pkgs.stdenvNoCC.mkDerivation rec {
          name = "sipyco-manual-html-${version}";
          version = sipyco.version;
          src = self;
          buildInputs = [
            sipyco
            pkgs.python3Packages.sphinx pkgs.python3Packages.sphinx_rtd_theme
            pkgs.python3Packages.sphinx-argparse pkgs.python3Packages.sphinxcontrib-wavedrom
          ];
          buildPhase = ''
            export SOURCE_DATE_EPOCH=${builtins.toString self.sourceInfo.lastModified}
            cd doc
            make html
          '';
          installPhase = ''
            cp -r _build/html $out
            mkdir $out/nix-support
            echo doc manual $out index.html >> $out/nix-support/hydra-build-products
          '';
        };
        sipyco-manual-pdf = pkgs.stdenvNoCC.mkDerivation rec {
          name = "sipyco-manual-pdf-${version}";
          version = sipyco.version;
          src = self;
          buildInputs = [
            sipyco
            pkgs.python3Packages.sphinx pkgs.python3Packages.sphinx_rtd_theme
            pkgs.python3Packages.sphinx-argparse pkgs.python3Packages.sphinxcontrib-wavedrom
            latex-sipyco-manual
          ];
          buildPhase = ''
            export SOURCE_DATE_EPOCH=${builtins.toString self.sourceInfo.lastModified}
            cd doc
            make latexpdf
          '';
          installPhase = ''
            mkdir $out
            cp _build/latex/SiPyCo.pdf $out
            mkdir $out/nix-support
            echo doc-pdf manual $out SiPyCo.pdf >> $out/nix-support/hydra-build-products
          '';
        };
      };

      devShells.x86_64-linux.default = pkgs.mkShell {
        name = "sipyco-dev-shell";
        buildInputs = [
          (pkgs.python3.withPackages(ps: with ps; [ pybase64 numpy ]))
          pkgs.python3Packages.sphinx pkgs.python3Packages.sphinx_rtd_theme
          pkgs.python3Packages.sphinx-argparse pkgs.python3Packages.sphinxcontrib-wavedrom
          latex-sipyco-manual
        ];
      };

      packages.aarch64-linux = {
        sipyco = sipyco-aarch64;
        default = sipyco-aarch64;
      };

      hydraJobs = {
        inherit (packages.x86_64-linux) sipyco sipyco-manual-html sipyco-manual-pdf;
      }; 
    };
}
