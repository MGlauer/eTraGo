import pandas as pd
import numpy as np
import os
import time
from pyomo.environ import (Var,Constraint, PositiveReals,ConcreteModel)

def buses_of_vlvl(network, voltage_level):
    """ Get bus-ids of given voltage level(s).

    Parameters
    ----------
    network : :class:`pypsa.Network
        Overall container of PyPSA
    voltage_level: list

    Returns
    -------
    list
        List containing bus-ids.
    """

    mask = network.buses.v_nom.isin(voltage_level)
    df = network.buses[mask]

    return df.index


def buses_grid_linked(network, voltage_level):
    """ Get bus-ids of a given voltage level connected to the grid.

    Parameters
    ----------
    network : :class:`pypsa.Network
        Overall container of PyPSA
    voltage_level: list

    Returns
    -------
    list
        List containing bus-ids.
    """

    mask = ((network.buses.index.isin(network.lines.bus0) |
            (network.buses.index.isin(network.lines.bus1))) &
            (network.buses.v_nom.isin(voltage_level)))

    df = network.buses[mask]

    return df.index


def connected_grid_lines(network, busids):
    """ Get grid lines connected to given buses.

    Parameters
    ----------
    network : :class:`pypsa.Network
        Overall container of PyPSA
    busids  : list
        List containing bus-ids.

    Returns
    -------
    :class:`pandas.DataFrame
        PyPSA lines.
    """

    mask = network.lines.bus1.isin(busids) |\
        network.lines.bus0.isin(busids)

    return network.lines[mask]


def connected_transformer(network, busids):
    """ Get transformer connected to given buses.

    Parameters
    ----------
    network : :class:`pypsa.Network
        Overall container of PyPSA
    busids  : list
        List containing bus-ids.

    Returns
    -------
    :class:`pandas.DataFrame
        PyPSA transformer.
    """

    mask = (network.transformers.bus0.isin(busids))

    return network.transformers[mask]


def load_shedding (network, **kwargs):
    """ Implement load shedding in existing network to identify feasibility problems
    ----------
    network : :class:`pypsa.Network
        Overall container of PyPSA
    marginal_cost : int
        Marginal costs for load shedding
    p_nom : int
        Installed capacity of load shedding generator
    Returns
    -------

    """

    marginal_cost_def = 10000#network.generators.marginal_cost.max()*2
    p_nom_def = network.loads_t.p_set.max().max()

    marginal_cost = kwargs.get('marginal_cost', marginal_cost_def)
    p_nom = kwargs.get('p_nom', p_nom_def)
    
    network.add("Carrier", "load")
    start = network.generators.index.astype(int).max()
    nums = len(network.buses.index)
    end = start+nums
    index = list(range(start,end))
    index = [str(x) for x in index]
    network.import_components_from_dataframe(
    pd.DataFrame(
    dict(marginal_cost=marginal_cost,
    p_nom=p_nom,
    carrier='load shedding',
    bus=network.buses.index),
    index=index),
    "Generator"
    )
    return


def data_manipulation_sh (network):
    from shapely.geometry import Point, LineString, MultiLineString
    from geoalchemy2.shape import from_shape, to_shape
    
    #add connection from Luebeck to Siems

    new_bus = str(int(network.buses.index.max())+1)
    new_trafo = str(int(network.transformers.index.max())+1)
    new_line = str(int(network.lines.index.max())+1)
    network.add("Bus", new_bus,carrier='AC', v_nom=220, x=10.760835, y=53.909745)
    network.add("Transformer", new_trafo, bus0="25536", bus1=new_bus, x=1.29960, tap_ratio=1, s_nom=1600)
    network.add("Line",new_line, bus0="26387",bus1=new_bus, x=0.0001, s_nom=1600)
    network.lines.loc[new_line,'cables']=3.0

    #bus geom
    point_bus1 = Point(10.760835,53.909745)
    network.buses.set_value(new_bus, 'geom', from_shape(point_bus1, 4326))

    #line geom/topo
    network.lines.set_value(new_line, 'geom', from_shape(MultiLineString([LineString([to_shape(network.buses.geom['26387']),point_bus1])]),4326))
    network.lines.set_value(new_line, 'topo', from_shape(LineString([to_shape(network.buses.geom['26387']),point_bus1]),4326))

    #trafo geom/topo
    network.transformers.set_value(new_trafo, 'geom', from_shape(MultiLineString([LineString([to_shape(network.buses.geom['25536']),point_bus1])]),4326))
    network.transformers.set_value(new_trafo, 'topo', from_shape(LineString([to_shape(network.buses.geom['25536']),point_bus1]),4326))

    return
    
def results_to_csv(network, path):
    """
    """
    if path==False:
        return None

    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

    network.export_to_csv_folder(path)
    data = pd.read_csv(os.path.join(path, 'network.csv'))
    data['time'] = network.results['Solver'].Time
    data.to_csv(os.path.join(path, 'network.csv'))

    if hasattr(network, 'Z'):
        file = [i for i in os.listdir(path.strip('0123456789')) if i=='Z.csv']
        if file:
           print('Z already calculated')
        else:
           network.Z.to_csv(path.strip('0123456789')+'/Z.csv', index=False)

    return

def parallelisation(network, start_h, end_h, group_size, solver_name, extra_functionality=None):

    print("Performing linear OPF, {} snapshot(s) at a time:".format(group_size))
    x = time.time()
    for i in range(int((end_h-start_h+1)/group_size)):
        network.lopf(network.snapshots[group_size*i:group_size*i+group_size], solver_name=solver_name, extra_functionality=extra_functionality)


    y = time.time()
    z = (y - x) / 60
    return

def pf_post_lopf(network, scenario):
    
    network_pf = network    

    #For the PF, set the P to the optimised P
    network_pf.generators_t.p_set = network_pf.generators_t.p_set.reindex(columns=network_pf.generators.index)
    network_pf.generators_t.p_set = network_pf.generators_t.p
    
    #Calculate q set from p_set with given cosphi
    #todo

    #Troubleshooting        
    #network_pf.generators_t.q_set = network_pf.generators_t.q_set*0
    #network.loads_t.q_set = network.loads_t.q_set*0
    #network.loads_t.p_set['28314'] = network.loads_t.p_set['28314']*0.5
    #network.loads_t.q_set['28314'] = network.loads_t.q_set['28314']*0.5
    #network.transformers.x=network.transformers.x['22596']*0.01
    #contingency_factor=2
    #network.lines.s_nom = contingency_factor*pups.lines.s_nom
    #network.transformers.s_nom = network.transformers.s_nom*contingency_factor
    
    #execute non-linear pf
    network_pf.pf(scenario.timeindex, use_seed=True)
    
    return network_pf

def calc_line_losses(network):
    """ Calculate losses per line with PF result data
    ----------
    network : :class:`pypsa.Network
        Overall container of PyPSA
    s0 : series
        apparent power of line
    i0 : series
        current of line  
    -------

    """
    #### Line losses
    # calculate apparent power S = sqrt(p² + q²) [in MW]
    s0_lines = ((network.lines_t.p0**2 + network.lines_t.q0**2).\
        apply(np.sqrt)) 
    # calculate current I = S / U [in A]
    i0_lines = np.multiply(s0_lines, 1000000) / np.multiply(network.lines.v_nom, 1000) 
    # calculate losses per line and timestep network.lines_t.line_losses = I² * R [in MW]
    network.lines_t.losses = np.divide(i0_lines**2 * network.lines.r, 1000000)
    # calculate total losses per line [in MW]
    network.lines = network.lines.assign(losses=np.sum(network.lines_t.losses).values)
    
    #### Transformer losses   
    # https://books.google.de/books?id=0glcCgAAQBAJ&pg=PA151&lpg=PA151&dq=wirkungsgrad+transformator+1000+mva&source=bl&ots=a6TKhNfwrJ&sig=r2HCpHczRRqdgzX_JDdlJo4hj-k&hl=de&sa=X&ved=0ahUKEwib5JTFs6fWAhVJY1AKHa1cAeAQ6AEIXjAI#v=onepage&q=wirkungsgrad%20transformator%201000%20mva&f=false
    # Crastan, Elektrische Energieversorgung, p.151
    # trafo 1000 MVA: 99.8 %
    network.transformers = network.transformers.assign(losses=np.multiply(network.transformers.s_nom,(1-0.998)).values)
        
    # calculate total losses (possibly enhance with adding these values to network container)
    losses_total = sum(network.lines.losses) + sum(network.transformers.losses)
    print("Total lines losses for all snapshots [MW]:",round(losses_total,2))
    losses_costs = losses_total * np.average(network.buses_t.marginal_price)
    print("Total costs for these losses [EUR]:",round(losses_costs,2))
  
    return
    
def loading_minimization(network,snapshots):

    network.model.number1 = Var(network.model.passive_branch_p_index, within = PositiveReals)
    network.model.number2 = Var(network.model.passive_branch_p_index, within = PositiveReals)

    def cRule(model, c, l, t):
        return (model.number1[c, l, t] - model.number2[c, l, t] == model.passive_branch_p[c, l, t])

    network.model.cRule=Constraint(network.model.passive_branch_p_index, rule=cRule)

    network.model.objective.expr += 0.00001* sum(network.model.number1[i] + network.model.number2[i] for i in network.model.passive_branch_p_index)

def group_parallel_lines(network):
    
    #ordering of buses: (not sure if still necessary, remaining from SQL code)
    old_lines = network.lines
    
    for line in old_lines.index:
        bus0_new = str(old_lines.loc[line,['bus0','bus1']].astype(int).min())
        bus1_new = str(old_lines.loc[line,['bus0','bus1']].astype(int).max())
        old_lines.set_value(line,'bus0',bus0_new)
        old_lines.set_value(line,'bus1',bus1_new)
        
    # saving the old index
    for line in old_lines:
        old_lines['old_index'] = network.lines.index
    
    grouped = old_lines.groupby(['bus0','bus1'])
    
    #calculating electrical properties for parallel lines
    grouped_agg = grouped.agg({ 'b': np.sum,
                                'b_pu': np.sum,
                                'cables': np.sum, 
                                'capital_cost': np.min, 
                                'frequency': np.mean, 
                                'g': np.sum,
                                'g_pu': np.sum, 
                                'geom': lambda x: x[0],
                                'length': lambda x: x.min(), 
                                'num_parallel': np.sum, 
                                'r': lambda x: np.reciprocal(np.sum(np.reciprocal(x))), 
                                'r_pu': lambda x: np.reciprocal(np.sum(np.reciprocal(x))), 
                                's_nom': np.sum,
                                's_nom_extendable': lambda x: x.min(), 
                                's_nom_max': np.sum, 
                                's_nom_min': np.sum, 
                                's_nom_opt': np.sum, 
                                'scn_name': lambda x: x.min(),  
                                'sub_network': lambda x: x.min(), 
                                'terrain_factor': lambda x: x.min(), 
                                'topo': lambda x: x[0],
                                'type': lambda x: x.min(),  
                                'v_ang_max': lambda x: x.min(), 
                                'v_ang_min': lambda x: x.min(), 
                                'x': lambda x: np.reciprocal(np.sum(np.reciprocal(x))),
                                'x_pu': lambda x: np.reciprocal(np.sum(np.reciprocal(x))),
                                'old_index': np.min})
    
    for i in range(0,len(grouped_agg.index)):
        grouped_agg.set_value(grouped_agg.index[i],'bus0',grouped_agg.index[i][0])
        grouped_agg.set_value(grouped_agg.index[i],'bus1',grouped_agg.index[i][1])
        
    new_lines=grouped_agg.set_index(grouped_agg.old_index)
    new_lines=new_lines.drop('old_index',1)
    network.lines = new_lines
    
    return
