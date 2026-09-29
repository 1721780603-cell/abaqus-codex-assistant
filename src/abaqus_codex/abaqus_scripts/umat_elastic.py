# -*- coding: utf-8 -*-
"""Small-strain solid tension: UMAT and built-in elastic reference.

Python 2.7/3 compatible. Run inside Abaqus/CAE, not system Python.
"""
from __future__ import print_function

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rectangle_tension import _load_config, _write_result, _read_results
from abaqus import mdb
from abaqusConstants import (THREE_D, DEFORMABLE_BODY, STANDARD, C3D8,
                            HEX, STRUCTURED, ON, OFF)
from caeModules import *
try:
    import builtins as _builtins
except ImportError:
    import __builtin__ as _builtins
from odbAccess import openOdb
import mesh
import regionToolset


def build_model(config, name, use_umat):
    m, a, p = config['model'], config['analysis'], config['material']
    length, height, depth = m['length'], m['height'], m['thickness']
    model = mdb.Model(name=name)
    sketch = model.ConstrainedSketch(name='Profile', sheetSize=2*max(length, height))
    sketch.rectangle(point1=(0, 0), point2=(length, height))
    part = model.Part(name='Block', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=depth)
    material = model.Material(name='ElasticMaterial')
    constants = (p['youngs_modulus'], p['poisson_ratio'])
    if use_umat:
        material.UserMaterial(mechanicalConstants=constants)
    else:
        material.Elastic(table=(constants,))
    model.HomogeneousSolidSection(name='Section', material='ElasticMaterial')
    part.SectionAssignment(region=regionToolset.Region(cells=part.cells), sectionName='Section')
    part.setMeshControls(regions=part.cells, elemShape=HEX, technique=STRUCTURED)
    part.setElementType(regions=(part.cells,), elemTypes=(mesh.ElemType(elemCode=C3D8, elemLibrary=STANDARD),))
    part.seedPart(size=a['mesh_size'])
    part.generateMesh()
    instance = model.rootAssembly.Instance(name='Block-1', part=part, dependent=ON)
    tol = min(length, height, depth)*1e-6
    # Symmetry planes remove rigid motion while allowing Poisson contraction.
    bounds = dict(xMin=-tol, xMax=length+tol, yMin=-tol,
                  yMax=height+tol, zMin=-tol, zMax=depth+tol)
    for set_name, bound, value, dof in (
        ('Left', 'xMax', tol, 'u1'), ('Bottom', 'yMax', tol, 'u2'),
        ('Back', 'zMax', tol, 'u3'), ('Right', 'xMin', length-tol, 'u1')):
        box = dict(bounds)
        box[bound] = value
        faces = instance.faces.getByBoundingBox(**box)
        if len(faces) != 1:
            raise RuntimeError('Expected exactly one boundary face: '+set_name)
        region = model.rootAssembly.Set(name=set_name, faces=faces)
        if set_name != 'Right':
            model.DisplacementBC(name=set_name, createStepName='Initial',
                                 region=region, **{dof: 0.0})
    model.StaticStep(name=a['step_name'], previous='Initial', nlgeom=OFF,
                     initialInc=0.1, maxInc=0.1)
    model.DisplacementBC(name='Pull', createStepName=a['step_name'],
                         region=model.rootAssembly.sets['Right'],
                         u1=a['right_edge_displacement'])
    model.FieldOutputRequest(name='TeachingOutput', createStepName=a['step_name'],
                             variables=('S', 'E', 'U', 'RF'))
    return model


def solve(config, model, job_name, source=None):
    kwargs = dict(name=job_name, model=model.name,
                  numCpus=config['analysis']['num_cpus'])
    if source:
        kwargs['userSubroutine'] = source
    job = mdb.Job(**kwargs)
    job.submit(consistencyChecking=ON)
    job.waitForCompletion()
    status_path = job_name+'.sta'
    if not os.path.isfile(status_path):
        raise RuntimeError('Missing job status: '+job_name)
    with open(status_path, 'rb') as stream:
        complete = b'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in stream.read()
    if not complete or not os.path.isfile(job_name+'.odb'):
        raise RuntimeError('Job did not complete: '+job_name)
    path = os.path.abspath(job_name+'.odb')
    result = _read_results(config, 'Block-1', path)
    result['job_name'] = job_name
    result['model_name'] = model.name
    odb = openOdb(path=path, readOnly=True)
    try:
        frame = odb.steps[config['analysis']['step_name']].frames[-1]
        if abs(float(frame.frameValue)-1.0) > 1e-6:
            raise RuntimeError('Incomplete final frame')
        stresses = frame.fieldOutputs['S'].values
        # Uniform homogeneous block: arithmetic IP mean is meaningful here only.
        result['mean_s11'] = _builtins.sum(float(v.data[0]) for v in stresses)/len(stresses)
        right = odb.rootAssembly.nodeSets['RIGHT']
        left = odb.rootAssembly.nodeSets['LEFT']
        result['right_rf1'] = _builtins.sum(float(v.data[0]) for v in frame.fieldOutputs['RF'].getSubset(region=right).values)
        result['left_rf1'] = _builtins.sum(float(v.data[0]) for v in frame.fieldOutputs['RF'].getSubset(region=left).values)
    finally:
        odb.close()
    return result


def main():
    args = [v for v in sys.argv[1:] if v != '--']
    if len(args) < 3:
        raise RuntimeError('Expected config, result, UMAT paths')
    config_path, result_path, source = [os.path.abspath(v) for v in args[-3:]]
    if not os.path.isfile(source):
        raise RuntimeError('Missing UMAT source')
    config = _load_config(config_path)
    name = config['model']['name']
    umat = build_model(config, name, True)
    reference = build_model(config, name+'_Reference', False)
    mdb.saveAs(pathName=os.path.abspath('umat_comparison.cae'))
    job_name = config['analysis']['job_name']
    result = solve(config, umat, job_name, source)
    # Sequential reference solve; no Fortran passed to built-in elastic material.
    baseline = solve(config, reference, job_name+'_ref')
    expected = config['material']['youngs_modulus']*config['analysis']['right_edge_displacement']/config['model']['length']
    area = config['model']['height']*config['model']['thickness']
    result['config'] = config
    result['reference'] = baseline
    result['theoretical_s11'] = expected
    result['theoretical_reaction'] = expected*area
    result['relative_s11_error'] = abs(result['mean_s11']-expected)/expected
    result['relative_reference_error'] = abs(result['mean_s11']-baseline['mean_s11'])/expected
    result['relative_reaction_error'] = abs(result['right_rf1']-expected*area)/(expected*area)
    result['relative_balance_error'] = abs(result['right_rf1']+result['left_rf1'])/(expected*area)
    result['user_subroutine'] = source
    _write_result(result_path, result)
    print('ABAQUS_CODEX_RESULT='+result_path)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
