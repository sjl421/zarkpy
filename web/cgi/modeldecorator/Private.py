#coding=utf-8
import web
import re
from Decorator import Decorator
import site_helper as sh

# 根据Userid对用户创建的数据私有化，即隐藏真实id，针对每个用户显示一个独立的id序列
# 重写insert delete update get gets all，把以上函数的primary key改为Userid和private_id来实现数据对用户的私有化
# Private装饰使用了Private表来记录每个用户对于每种model的max_id值，以便在insert时得到private_id,实现类似auto_increment的效果

# 对于all和getCount函数,Private改写了其where语句,这会增加程序的"不透明"性
# 因此为了避免用户不小心忘记了Private的存在，所以断言where中禁止出现user_id_key
# 但是，如果你确信你要自己控制user_id_key, 那么给env加上_ignore_private_uk=True, good luck

# Private通过改变返回数据的_primary_key来修改id值，但是它改变的只是数据, 而不改变类及其行为
# Private不应该改写self.model.primary_key, 这样会导致"被继承类"的行为不明确

# 使用此装饰，必须在table_template中添加Userid和private_id字段, 并添加(Userid, private_id)唯一索引
# 装饰后，primary_key将被改为private_id, id属性将调用private_id, 但是原有的{$table_name}id值不变
# 也可自定义user_id_key和primary_key的列名

# 注意，若要在已有表上添加Private装饰，请先处理好所有已有数据的Userid和private_id的值
# 最后，记得添加类似索引: unique key  (Userid, private_id)

class Private(Decorator):
    '''decorator = [
        ('Private', dict(user_id_key='Userid', primary_key='private_id') ),
    ]'''

    def __init__(self, model, arguments):
        Decorator.__init__(self, model, arguments)
        assert(self.arguments.primary_key in self.model.column_names)
        assert(self.arguments.user_id_key in self.model.column_names)

    def insert(self, data):
        data = sh.copy(data)
        self._setUseridToData(data)
        self._setPrivateidToData(data)
        self.model.insert(data)
        self._incPrivateid(data)
        return data[self.arguments.primary_key]

    def replaceInsert(self, data):
        data = sh.copy(data)
        self._setUseridToData(data)
        self._setPrivateidToData(data)
        self.model.replaceInsert(data)
        self._incPrivateid(data)
        return data[self.arguments.primary_key]

    def delete(self, item_id):
        assert(sh.session.is_login)
        exists_item = self._getItemByPrivateid(item_id)
        return self.model.delete(exists_item.id) if exists_item is not None else 0

    def update(self, item_id, data):
        data = sh.copy(data)
        assert(sh.session.is_login)
        exists_item = self._getItemByPrivateid(item_id)
        return self.model.update(exists_item.id, data) if exists_item is not None else 0

    def get(self, item_id):
        assert(sh.session.is_login)
        exists_item = self._getItemByPrivateid(item_id)
        return self._changePrimaryKey(self.model.get(exists_item.id)) \
                if exists_item is not None else None
    # def gets? 不需要重写gets函数，因为gets继承了get所做的事情

    def getOneByWhere(self, where, argv=[]):
        uk = self.arguments.user_id_key
        assert re.search(r'\b%s\b' % uk, where) is None, u'你不想让getOneByWhere为where自动添加Userid? 请使用all函数和_ignore_private_uk=True'
        where = '(%s) and %s=%%s' % (where, uk)
        argv = argv + [sh.session.id]
        return self._changePrimaryKey(self.model.getOneByWhere(where, argv))

    def all(self, env=None):
        return self._changePrimaryKey(self.model.all(self._setWhereWithUserid(env)))

    def getCount(self, env=None):
        return self.model.getCount(self._setWhereWithUserid(env))

    def _setUseridToData(self, data):
        uk = self.arguments.user_id_key
        if not data.has_key(uk):
            assert sh.session.is_login, u'必须已登录，或显示给出%s' % uk
            data[uk] = sh.session.id
    
    def _setPrivateidToData(self, data):
        uk = self.arguments.user_id_key
        pk = self.arguments.primary_key
        assert not data.has_key(pk), u'你确定你要自己控制%s的值?' % pk
        data[pk] = sh.model('Private').getNextPrivateid(self._getModelTableName(), data[uk])

    def _incPrivateid(self, data):
        uk = self.arguments.user_id_key
        sh.model('Private').incPrivateid(self._getModelTableName(), data[uk])

    def _getItemByPrivateid(self, pri_id):
        return self.model.getOneByWhere(self.arguments.user_id_key+'=%s and '+self.arguments.primary_key+'=%s', [sh.session.id, pri_id])

    def _setWhereWithUserid(self, env):
        env = sh.copy(env) if env else {}
        assert(sh.session.is_login)
        uk = self.arguments.user_id_key
        user_id = sh.session.id
        if not env.get('_ignore_private_uk', False):
            if env.has_key('where'):
                assert re.search(r'\b%s\b' % uk, env['where'][0]) is None, u"想自定义Userid? 请使用env['_ignore_private_uk']=True%s" + env['where'][0] 
                env['where'][0] = '(%s) and %s=%%s' % (env['where'][0], uk)
                env['where'][1].append(user_id)
            else:
                env['where'] = (uk+'=%s', [user_id])
        return env

    def _changePrimaryKey(self, datas):
        if datas is not None:
            if isinstance(datas, list) or isinstance(datas, tuple):
                for d in datas:
                    if d is not None:
                        d._primary_key = self.arguments.primary_key
            elif isinstance(datas, dict) or isinstance(datas, web.Storage):
                datas._primary_key = self.arguments.primary_key
        return datas
