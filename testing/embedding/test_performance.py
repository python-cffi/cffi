from testing.embedding.test_basic import EmbeddingTests


class TestPerformance(EmbeddingTests):
    def test_perf_single_threaded(self):
        self.prepare_module('perf')
        self.compile('perf-test', ['_perf_cffi'], opt=True)
        output = self.execute('perf-test')
        print '='*79
        print output.rstrip()
        print '='*79

    def test_perf_in_1_thread(self):
        self.prepare_module('perf')
        self.compile('perf-test', ['_perf_cffi'], opt=True, threads=True,
                     defines={'PTEST_USE_THREAD': '1'})
        output = self.execute('perf-test')
        print '='*79
        print output.rstrip()
        print '='*79

    def test_perf_in_2_threads(self):
        self.prepare_module('perf')
        self.compile('perf-test', ['_perf_cffi'], opt=True, threads=True,
                     defines={'PTEST_USE_THREAD': '2'})
        output = self.execute('perf-test')
        print '='*79
        print output.rstrip()
        print '='*79

    def test_perf_in_4_threads(self):
        self.prepare_module('perf')
        self.compile('perf-test', ['_perf_cffi'], opt=True, threads=True,
                     defines={'PTEST_USE_THREAD': '4'})
        output = self.execute('perf-test')
        print '='*79
        print output.rstrip()
        print '='*79

    def test_perf_in_8_threads(self):
        self.prepare_module('perf')
        self.compile('perf-test', ['_perf_cffi'], opt=True, threads=True,
                     defines={'PTEST_USE_THREAD': '8'})
        output = self.execute('perf-test')
        print '='*79
        print output.rstrip()
        print '='*79
