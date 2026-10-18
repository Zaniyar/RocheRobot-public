"""STEP lokal mit dem in Isaac Sim enthaltenen HOOPS-Konverter nach USD."""
import json
import hashlib
from pathlib import Path
from isaacsim import SimulationApp

app = SimulationApp({"headless": True})
try:
    import omni.kit.app
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.set_extension_enabled_immediate("omni.kit.converter.hoops_core", True)
    from omni.converter import hoops
    from pxr import Usd, UsdGeom
    source = Path(__file__).resolve().parents[1] / "example_object.stp"
    out_dir = Path(r"D:\RobotRuntime\ObjectAssets")
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "example_object.usd"
    if output.exists():
        raise RuntimeError("CAD-Ziel existiert bereits; vorhandene Konvertierung zuerst prüfen.")
    params = hoops.Parameters()
    params.tessLOD = 3
    params.convertHidden = False
    params.instancingStyle = hoops.InstancingStyle.eNone
    params.materialType = hoops.MaterialType.ePreviewSurface
    params.useMaterials = True
    result = hoops.convert(params, str(source), str(output),
                           {"dMetersPerUnit": "1.0", "iUpAxis": "2"})
    print("CAD_CONVERTER_RESULT", result, flush=True)
    if not output.is_file():
        raise RuntimeError("CAD-Konverter hat keine USD-Datei erzeugt.")
    stage = Usd.Stage.Open(str(output))
    meshes = [str(p.GetPath()) for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeWorldBound(stage.GetDefaultPrim()).ComputeAlignedRange()
    report = {"source": source.name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "usd": str(output), "converter_result": list(result),
              "meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
              "up_axis": str(UsdGeom.GetStageUpAxis(stage)), "default_prim": str(stage.GetDefaultPrim().GetPath()),
              "mesh_count": len(meshes), "meshes": meshes,
              "bounds_min": list(bbox.GetMin()), "bounds_max": list(bbox.GetMax()),
              "extent_stage_units": list(bbox.GetSize()), "tessellation_lod": 3}
    (out_dir / "cad-import-report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print("ROCHE_CAD_REPORT", json.dumps(report), flush=True)
    if not meshes:
        raise RuntimeError("USD enthält kein sichtbares Mesh.")
finally:
    app.close()
