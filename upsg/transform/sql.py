from copy import deepcopy
import uuid

import sqlalchemy

from ..stage import RunnableStage
from ..uobject import UObject, UObjectPhase
from ..utils import random_table_name


class RunSQL(RunnableStage):

    """
    
    Run a SQL query. Tables utilized and generated can be generated by
    UPSG

    Input keys and output keys are init arguments
    
    Parameters
    ----------
    query : str
        The sql query to run. Should be a formatting string with keywords
        corresponding to the names of tables that UPSG is handling.

    db_url : str or None
        The url of the database. Should conform to the format of
        SQLAlchemy database URLS
        (http://docs.sqlalchemy.org/en/rel_0_9/core/engines.html#database-urls)
        If None, a temporary database will be created

    in_keys : list of str
        The names of input keys. Also, should correspond to the keywords
        in query representing tables that are inputs of the query.

    out_keys : list of str
        The names of output keys. Also, should correspond to the keywords
        in query representing tables that are outputs of the query.

    conn_params : dict of str to ? 
        A dictionary of the keyword arguments to be passed to the connect
        method of some library implementing the Python Database API
        Specification 2.0
        (https://www.python.org/dev/peps/pep-0249/#connect)

    in_keys and out_keys should not share any elements

    Examples
    --------
    Say that we are generating two tables elsewhere in the
    pipeline. We don't know a priori what the names of these tables
    are, since they're generated. However, we know that one table will
    correspond to the input key 'employees' and the other will
    correspond to the input key 'hours'. We intend to join these
    tables and generate a third table, corresponding to the output key
    'report'. We would initialize our stage like:

    >>> query = ('CREATE TABLE {report} AS '
    ...     'SELECT {employees} JOIN {hours} '
    ...     'ON {employees}.id = {hours}.employee_id ')
    >>> stage = RunSQL(db_url, query, in_keys = ['employees', 'hours'],
    ...     out_keys = ['report'])

    
    """

    def __init__(self, query, db_url=None, in_keys=[], out_keys=[], conn_params={}):

        self.__query = query
        self.__in_keys = in_keys
        self.__out_keys = out_keys
        if db_url is None:
            db_url = 'sqlite:///UPSG_{}.db'.format(uuid.uuid4())
        self.__db_url = db_url
        self.__conn_params = conn_params

    @property
    def input_keys(self):
        return self.__in_keys

    @property
    def output_keys(self):
        return self.__out_keys

    def run(self, outputs_requested, **kwargs):
        db_url = self.__db_url
        conn_params = self.__conn_params
        conn = sqlalchemy.create_engine(db_url, connect_args=conn_params)
        sql_info = {key: kwargs[key].to_sql(db_url, conn_params) for 
                    key in kwargs}

        table_names = {key: sql_info[key].table.name for key in sql_info}
        table_names.update({key: random_table_name() for
                            key in self.__out_keys})
        query = self.__query.format(**table_names)

        # sqlalchemy only lets us execute one statement at a time
        # TODO execute these within a transaction so we don't break ACID
        [conn.execute(sqlalchemy.sql.text(statement))
         for statement in query.split(';')]

        output = {key: UObject(UObjectPhase.Write) for key in self.__out_keys}
        [output[key].from_sql(db_url, conn_params, table_names[key], True) for
         key in self.__out_keys]
        return output
