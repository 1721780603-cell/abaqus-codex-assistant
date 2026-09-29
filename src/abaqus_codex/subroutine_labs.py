"""Fixed, inspectable Abaqus/Standard user-subroutine teaching labs.

Export only: no Abaqus process or license is started by this module.
"""

from __future__ import annotations

from pathlib import Path


LABS = (
    "disp_ramp", "dflux_wall", "film_wall", "usdfld_elastic",
    "uvarm_stress_ratio", "uexpan_thermal_bar", "hetval_heated_wall",
)


def _truss(material: str, load: str, output: str = "U, RF",
           element_output: str = "S, E") -> str:
    return ("*HEADING\nTwo-node axial truss teaching lab\n"
            "*NODE\n1, 0., 0.\n2, 100., 0.\n"
            "*ELEMENT, TYPE=T2D2, ELSET=BAR\n1, 1, 2\n"
            "*SOLID SECTION, ELSET=BAR, MATERIAL=STEEL\n10.\n"
            "*MATERIAL, NAME=STEEL\n" + material +
            "*BOUNDARY\n1, 1, 2, 0.\n2, 2, 2, 0.\n"
            "*STEP, NAME=AXIAL, NLGEOM=NO\n*STATIC\n0.1, 1.0\n" + load +
            "*OUTPUT, FIELD\n*NODE OUTPUT\n" + output + "\n"
            "*ELEMENT OUTPUT\n" + element_output +
            "\n*END STEP\n")


def _wall(load: str, extra_material: str = "") -> str:
    # C3D8/DC3D8 face S4 consists of nodes 2,3,7,6 (x=0.1 m).
    return ("*HEADING\nOne-element steady heat-conduction teaching lab\n"
            "*NODE\n1, 0., 0., 0.\n2, 0.1, 0., 0.\n"
            "3, 0.1, 1., 0.\n4, 0., 1., 0.\n"
            "5, 0., 0., 1.\n6, 0.1, 0., 1.\n"
            "7, 0.1, 1., 1.\n8, 0., 1., 1.\n"
            "*ELEMENT, TYPE=DC3D8, ELSET=WALL\n1, 1,2,3,4,5,6,7,8\n"
            "*SOLID SECTION, ELSET=WALL, MATERIAL=THERMAL\n"
            "*MATERIAL, NAME=THERMAL\n*CONDUCTIVITY\n10.\n" + extra_material +
            "*BOUNDARY\n1, 11, 11, 20.\n4, 11, 11, 20.\n"
            "5, 11, 11, 20.\n8, 11, 11, 20.\n"
            "*STEP, NAME=STEADY\n*HEAT TRANSFER, STEADY STATE\n"
            "0.1, 1.0\n" + load +
            "*OUTPUT, FIELD\n*NODE OUTPUT\nNT, RFL\n"
            "*ELEMENT OUTPUT\nHFL\n*END STEP\n")


INPUTS = {
    "disp_ramp": (
        _truss("*ELASTIC\n210000., 0.3\n",
               "*BOUNDARY, USER\n2, 1, 1, 0.1\n"),
        _truss("*ELASTIC\n210000., 0.3\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n"),
        "disp_ramp.for", "U1 at node 2 = 0.1 mm; S11 = 210 MPa; RF1 = 2100 N.",
        "mm, N, MPa; area=10 mm2; length=100 mm; prescribed displacement=0.1 mm."
    ),
    "dflux_wall": (
        _wall("*DFLUX\n1, S4NU, 1000.\n"),
        _wall("*DFLUX\n1, S4, 1000.\n"),
        "dflux_wall.for", "Right-face temperature = 30 C; heat flux = 1000 W/m2.",
        "m, W, s, C; k=10 W/(m K); left=20 C; inward right flux=1000 W/m2."
    ),
    "film_wall": (
        _wall("*BOUNDARY, OP=MOD\n1, 11, 11, 100.\n"
              "4, 11, 11, 100.\n5, 11, 11, 100.\n"
              "8, 11, 11, 100.\n*FILM\n1, F4NU, 20., 100.\n"),
        _wall("*BOUNDARY, OP=MOD\n1, 11, 11, 100.\n"
              "4, 11, 11, 100.\n5, 11, 11, 100.\n"
              "8, 11, 11, 100.\n*FILM\n1, F4, 20., 100.\n"),
        "film_wall.for", "Right-face temperature = 60 C; outward flux = 4000 W/m2.",
        "m, W, s, C; k=10 W/(m K); left=100 C; ambient=20 C; h=100 W/(m2 K)."
    ),
    "usdfld_elastic": (
        _truss("*ELASTIC, DEPENDENCIES=1\n210000., 0.3, 0., 0.\n"
               "105000., 0.3, 0., 1.\n*USER DEFINED FIELD\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n", element_output="S, E, FV"),
        _truss("*ELASTIC\n105000., 0.3\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n"),
        "usdfld_elastic.for", "FV1 = 1; S11 = 105 MPa; RF1 = 1050 N.",
        "mm, N, MPa; area=10 mm2; length=100 mm; E(field=1)=105000 MPa."
    ),
    "uvarm_stress_ratio": (
        _truss("*ELASTIC\n210000., 0.3\n*USER OUTPUT VARIABLES\n1\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n", element_output="S, E, UVARM"),
        _truss("*ELASTIC\n210000., 0.3\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n"),
        "uvarm_stress_ratio.for",
        "S11 = 210 MPa; UVARM1 = S11/210 MPa = 1. Reference S11 also 210 MPa.",
        "mm, N, MPa; area=10 mm2; length=100 mm; E=210000 MPa; U1=0.1 mm."
    ),
    "uexpan_thermal_bar": (
        _truss("*ELASTIC\n210000., 0.3\n*EXPANSION, USER\n"
               "*INITIAL CONDITIONS, TYPE=TEMPERATURE\n1, 20.\n2, 20.\n",
               "*TEMPERATURE\n1, 70.\n2, 70.\n"),
        _truss("*ELASTIC\n210000., 0.3\n*EXPANSION\n1.0E-5\n"
               "*INITIAL CONDITIONS, TYPE=TEMPERATURE\n1, 20.\n2, 20.\n",
               "*TEMPERATURE\n1, 70.\n2, 70.\n"),
        "uexpan_thermal_bar.for",
        "Free-end U1 = alpha * 50 C * 100 mm = 0.05 mm; S11 approximately 0.",
        "mm, N, MPa, C; alpha=1e-5 /C; initial 20 C, final 70 C; right end free."
    ),
    "hetval_heated_wall": (
        _wall("", extra_material="*HEAT GENERATION\n"),
        _wall("*DFLUX\n1, BF, 1000.\n"),
        "hetval_heated_wall.for",
        "Right-face temperature = 20.5 C; mean-element heat flux HFL1 = -50 W/m2.",
        "m, W, s, C; k=10 W/(m K); left=20 C; source=1000 W/m3; right insulated."
    ),
}


def export_lab(name: str, destination: Path) -> Path:
    """Create a new lab directory; refuse to merge into existing user data."""
    if name not in INPUTS:
        raise ValueError("Unknown lab: {0}; choose from {1}".format(name, ", ".join(LABS)))
    if destination.exists():
        raise FileExistsError("实验目录已存在，请选择新目录：{0}".format(destination))
    source = Path(__file__).resolve().parent / "user_subroutines" / INPUTS[name][2]
    if not source.is_file():
        raise FileNotFoundError("缺少子程序模板：{0}".format(source))
    generated, reference, filename, theory, units = INPUTS[name]
    destination.mkdir(parents=True)
    (destination / "user.inp").write_text(generated, encoding="ascii", newline="\n")
    (destination / "reference.inp").write_text(reference, encoding="ascii", newline="\n")
    (destination / filename).write_text(source.read_text(encoding="ascii"),
                                        encoding="ascii", newline="\n")
    (destination / "README.md").write_text(
        "# {0}\n\n".format(name) +
        "Experimental Abaqus/Standard teaching case. Not yet verified on a real Abaqus installation.\n\n" +
        "Units and inputs: {0}\n\nAnalytical expectation: {1}\n\n".format(units, theory) +
        "Check compiler and Abaqus license first. In this new directory, run the user job\n" +
        "`abaqus job=user input=user.inp user={0} interactive`\n".format(filename) +
        "then the built-in reference `abaqus job=reference input=reference.inp interactive`.\n" +
        "Compare final-frame U/RF/S/UVARM1 or NT11/HFL and status files. " +
        "Generation alone proves neither convergence nor numerical agreement.\n",
        encoding="utf-8", newline="\n")
    return destination
