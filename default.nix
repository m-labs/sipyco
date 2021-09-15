{ pkgs ? import <nixpkgs> { }}:

with pkgs;
python3Packages.buildPythonPackage {
  pname = "sipyco";
  version = "1.2";
  disabled = python3Packages.pythonOlder "3.7";

  src = lib.cleanSource ./.;

  propagatedBuildInputs = with python3Packages; [ numpy pluggy pybase64 ];

  checkInputs = with python3Packages; [ pytestCheckHook ];
  disabledTests = [ "test_asyncio_echo" ];

  meta = with lib; {
    description = "Simple Python Communications";
    homepage = "https://github.com/m-labs/sipyco";
    license = licenses.lgpl3Only;
  };
}
